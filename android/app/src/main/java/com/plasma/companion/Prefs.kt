package com.plasma.companion

import android.content.Context

/** The handful of things worth remembering between launches. */
class Prefs(context: Context) {

    private val sp = context.getSharedPreferences("plasma", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = sp.getString(KEY_URL, "") ?: ""
        set(value) = sp.edit().putString(KEY_URL, value.trim().trimEnd('/')).apply()

    /**
     * SHA-256 of the certificate we accepted for [serverUrl].
     *
     * Cleared whenever the address changes: a different machine is a different
     * certificate, and silently keeping the old pin would reject the new
     * server for reasons nobody could guess.
     */
    var certPin: String?
        get() = sp.getString(KEY_PIN, null)
        set(value) = sp.edit().putString(KEY_PIN, value).apply()

    val widthDp: Int get() = sp.getInt(KEY_W, 190)
    val heightDp: Int get() = sp.getInt(KEY_H, 320)

    var posX: Int
        get() = sp.getInt(KEY_X, 24)
        set(value) = sp.edit().putInt(KEY_X, value).apply()

    var posY: Int
        get() = sp.getInt(KEY_Y, 0)
        set(value) = sp.edit().putInt(KEY_Y, value).apply()

    fun savePosition(x: Int, y: Int) {
        sp.edit().putInt(KEY_X, x).putInt(KEY_Y, y).apply()
    }

    fun setSize(widthDp: Int, heightDp: Int) {
        sp.edit().putInt(KEY_W, widthDp).putInt(KEY_H, heightDp).apply()
    }

    /** Changing the address invalidates the pinned certificate. */
    fun setServer(url: String) {
        val cleaned = url.trim().trimEnd('/')
        if (cleaned != serverUrl) certPin = null
        serverUrl = cleaned
    }

    fun forgetCertificate() {
        certPin = null
    }

    private companion object {
        const val KEY_URL = "server_url"
        const val KEY_PIN = "cert_pin"
        const val KEY_W = "width_dp"
        const val KEY_H = "height_dp"
        const val KEY_X = "pos_x"
        const val KEY_Y = "pos_y"
    }
}
