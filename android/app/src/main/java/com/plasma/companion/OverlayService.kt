package com.plasma.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.PixelFormat
import android.net.http.SslError
import android.os.Build
import android.os.IBinder
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.net.URI
import java.security.MessageDigest
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * The floating avatar.
 *
 * A foreground service holding one `TYPE_APPLICATION_OVERLAY` window, which
 * contains nothing but a transparent WebView pointed at Plasma's `?overlay=1`
 * page. All the 3D, the lip-sync and the animation stay in the web app — this
 * is a window, not a second implementation of the avatar.
 *
 * Drag her to move her. Tap her to talk. The notification stops her.
 */
class OverlayService : Service() {

    private lateinit var windowManager: WindowManager
    private var webView: WebView? = null
    private var params: WindowManager.LayoutParams? = null

    companion object {
        private const val TAG = "PlasmaOverlay"
        private const val CHANNEL_ID = "plasma_overlay"
        private const val NOTIFICATION_ID = 1
        const val ACTION_STOP = "com.plasma.companion.STOP"
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (webView != null) return START_STICKY      // already showing

        // The service declares foregroundServiceType="microphone", and from
        // Android 14 startForeground() throws outright if RECORD_AUDIO is not
        // already held. Refusing here with a sentence beats crashing.
        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            toast("Grant Plasma the microphone first, then show her.")
            stopSelf()
            return START_NOT_STICKY
        }

        startForeground(NOTIFICATION_ID, buildNotification())

        val prefs = Prefs(this)
        val base = prefs.serverUrl
        if (base.isBlank()) {
            toast("Set Plasma's address in the app first.")
            stopSelf()
            return START_NOT_STICKY
        }

        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        show(base, prefs)
        return START_STICKY
    }

    // ── The window ───────────────────────────────────────────────────────
    private fun show(base: String, prefs: Prefs) {
        val density = resources.displayMetrics.density
        val lp = WindowManager.LayoutParams(
            (prefs.widthDp * density).roundToInt(),
            (prefs.heightDp * density).roundToInt(),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            // NOT_FOCUSABLE keeps the home screen and every other app fully
            // usable — she never steals the keyboard or the back button. The
            // window is only as big as she is, so the rest of the screen is
            // not covered at all.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.START
            x = prefs.posX
            y = prefs.posY
        }
        params = lp

        val view = WebView(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            // Transparent WebViews must not be hardware-layered onto an opaque
            // surface, or the "transparent" area comes out black.
            setLayerType(View.LAYER_TYPE_HARDWARE, null)
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
            overScrollMode = View.OVER_SCROLL_NEVER

            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false   // she speaks unprompted
            settings.useWideViewPort = false
            settings.loadWithOverviewMode = false

            webViewClient = PinnedWebViewClient(this@OverlayService, base)
            webChromeClient = MicGrantingChromeClient(this@OverlayService)
        }
        webView = view
        view.setOnTouchListener(DragToMove(lp))

        view.loadUrl(joinUrl(base, "/?overlay=1"))
        try {
            windowManager.addView(view, lp)
        } catch (e: Exception) {
            Log.e(TAG, "Could not add the overlay window", e)
            toast("Allow \"Display over other apps\" for Plasma, then try again.")
            webView = null
            stopSelf()
        }
    }

    /** Drag anywhere on her to move the window; a tap falls through to the page. */
    private inner class DragToMove(
        private val lp: WindowManager.LayoutParams,
    ) : View.OnTouchListener {
        private val slop = ViewConfiguration.get(this@OverlayService).scaledTouchSlop
        private var startX = 0
        private var startY = 0
        private var touchX = 0f
        private var touchY = 0f
        private var dragging = false

        override fun onTouch(v: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = lp.x
                    startY = lp.y
                    touchX = event.rawX
                    touchY = event.rawY
                    dragging = false
                    return false            // let the page see the press too
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - touchX
                    val dy = event.rawY - touchY
                    if (!dragging && (abs(dx) > slop || abs(dy) > slop)) dragging = true
                    if (dragging) {
                        lp.x = startX + dx.roundToInt()
                        // Gravity is BOTTOM, so y grows upwards.
                        lp.y = startY - dy.roundToInt()
                        runCatching { windowManager.updateViewLayout(v, lp) }
                        return true         // consumed: this is a move, not a tap
                    }
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (dragging) {
                        Prefs(this@OverlayService).savePosition(lp.x, lp.y)
                        return true         // swallow the up so it is not a tap
                    }
                }
            }
            return false
        }
    }

    // ── HTTPS to a self-signed server ────────────────────────────────────
    /**
     * Plasma serves HTTPS with a certificate it signs itself, so Android will
     * reject it — correctly, since it has no way to know it is yours.
     *
     * Blanket-accepting every certificate error would make this app trust any
     * machine that answers on that address, which on a café Wi-Fi is exactly
     * the attack the warning exists for. Instead the first certificate seen
     * for the configured host is remembered by fingerprint, and from then on
     * only that one is accepted. A changed certificate stops the load and
     * says so, rather than proceeding quietly.
     */
    private class PinnedWebViewClient(
        private val service: OverlayService,
        private val base: String,
    ) : WebViewClient() {

        private val expectedHost: String? = runCatching { URI(base).host }.getOrNull()

        override fun onReceivedSslError(
            view: WebView,
            handler: SslErrorHandler,
            error: SslError,
        ) {
            val host = runCatching { URI(error.url).host }.getOrNull()
            if (host == null || host != expectedHost) {
                handler.cancel()
                return
            }
            val cert = error.certificate.x509Certificate
            if (cert == null) {
                handler.cancel()
                return
            }
            val fingerprint = sha256(cert.encoded)
            val prefs = Prefs(service)
            val pinned = prefs.certPin
            when {
                pinned.isNullOrBlank() -> {          // trust on first use
                    prefs.certPin = fingerprint
                    handler.proceed()
                }
                pinned == fingerprint -> handler.proceed()
                else -> {
                    handler.cancel()
                    service.toast(
                        "Plasma's certificate changed. If you regenerated it, " +
                            "clear the saved certificate in the app.",
                    )
                }
            }
        }

        override fun shouldOverrideUrlLoading(
            view: WebView,
            request: WebResourceRequest,
        ): Boolean {
            // Never let the floating window navigate away from Plasma.
            return runCatching { request.url.host != expectedHost }.getOrDefault(true)
        }

        private fun sha256(bytes: ByteArray): String =
            MessageDigest.getInstance("SHA-256").digest(bytes)
                .joinToString("") { "%02x".format(it) }
    }

    /** The page asks for the microphone; hand it over only if we hold it. */
    private class MicGrantingChromeClient(
        private val service: OverlayService,
    ) : WebChromeClient() {
        override fun onPermissionRequest(request: PermissionRequest) {
            val wantsMic = request.resources
                .contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)
            val granted = ContextCompat.checkSelfPermission(
                service, android.Manifest.permission.RECORD_AUDIO,
            ) == PackageManager.PERMISSION_GRANTED
            if (wantsMic && granted) {
                request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
            } else {
                request.deny()
                if (wantsMic) service.toast("Grant Plasma the microphone to talk to her.")
            }
        }
    }

    // ── Housekeeping ─────────────────────────────────────────────────────
    private fun buildNotification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID, "Plasma", NotificationManager.IMPORTANCE_LOW,
                ).apply { description = "Keeps the floating avatar on screen." },
            )
        }
        val stop = PendingIntent.getService(
            this, 0,
            Intent(this, OverlayService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Plasma is on screen")
            .setContentText("Drag to move her, tap to talk.")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(0, "Hide", stop)
            .build()
    }

    private fun joinUrl(base: String, path: String) =
        base.trimEnd('/') + path

    fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    override fun onDestroy() {
        webView?.let {
            runCatching { windowManager.removeView(it) }
            it.destroy()
        }
        webView = null
        super.onDestroy()
    }
}
