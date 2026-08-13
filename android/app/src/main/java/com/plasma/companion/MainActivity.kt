package com.plasma.companion

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/**
 * Setup, and nothing else. Everything you actually do with her happens in the
 * floating window; this screen exists to collect an address and two Android
 * permissions that only the user can grant.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs
    private lateinit var urlField: EditText
    private lateinit var statusView: TextView

    private val askMic = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { refreshStatus() }

    private val askNotifications = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { refreshStatus() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)

        urlField = findViewById(R.id.url)
        statusView = findViewById(R.id.status)
        urlField.setText(prefs.serverUrl.ifBlank { "https://192.168.1.10:8443" })

        findViewById<Button>(R.id.grant_overlay).setOnClickListener {
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName"),
                ),
            )
        }

        findViewById<Button>(R.id.grant_mic).setOnClickListener {
            askMic.launch(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        findViewById<Button>(R.id.show).setOnClickListener {
            val url = urlField.text.toString().trim()
            if (!url.startsWith("https://")) {
                // Without HTTPS the page is not a secure context, and Chrome
                // will refuse the microphone — she would appear but not hear.
                toast("Use the https:// address that serve_phone.py prints.")
                return@setOnClickListener
            }
            if (!Settings.canDrawOverlays(this)) {
                toast("Allow \"Display over other apps\" first.")
                return@setOnClickListener
            }
            prefs.setServer(url)
            ContextCompat.startForegroundService(
                this, Intent(this, OverlayService::class.java),
            )
            moveTaskToBack(true)     // get out of the way so you can see her
        }

        findViewById<Button>(R.id.hide).setOnClickListener {
            startService(
                Intent(this, OverlayService::class.java)
                    .setAction(OverlayService.ACTION_STOP),
            )
        }

        findViewById<Button>(R.id.forget_cert).setOnClickListener {
            prefs.forgetCertificate()
            toast("Forgotten. The next connection will trust a new certificate.")
        }

        val size = findViewById<SeekBar>(R.id.size)
        val sizeLabel = findViewById<TextView>(R.id.size_label)
        size.progress = prefs.heightDp
        sizeLabel.text = getString(R.string.size_label, prefs.heightDp)
        size.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar, value: Int, fromUser: Boolean) {
                sizeLabel.text = getString(R.string.size_label, value)
            }

            override fun onStartTrackingTouch(sb: SeekBar) = Unit
            override fun onStopTrackingTouch(sb: SeekBar) {
                // Keep her roughly human-shaped rather than letting the window
                // squash her: width follows height.
                val h = sb.progress.coerceAtLeast(140)
                prefs.setSize((h * 0.6f).toInt(), h)
                toast("Tap \"Show Plasma\" again to resize her.")
            }
        })
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    private fun refreshStatus() {
        val overlay = Settings.canDrawOverlays(this)
        val mic = ContextCompat.checkSelfPermission(
            this, Manifest.permission.RECORD_AUDIO,
        ) == PackageManager.PERMISSION_GRANTED
        statusView.text = buildString {
            append(if (overlay) "✓" else "✗").append(" draw over other apps\n")
            append(if (mic) "✓" else "✗").append(" microphone")
        }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
