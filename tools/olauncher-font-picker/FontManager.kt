package app.olauncher.helper

import android.content.Context
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.res.ResourcesCompat
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.fragment.app.FragmentManager
import app.olauncher.R
import java.io.File

object FontManager {
    private const val PREFS_NAME = "font_preferences"
    private const val KEY_SELECTED = "selected_font"
    const val DEFAULT_ID = "builtin:olauncher"

    data class FontOption(
        val id: String,
        val name: String,
        val imported: Boolean = false,
    )

    private val builtInOptions = listOf(
        FontOption(DEFAULT_ID, "Olauncher default"),
        FontOption("builtin:ubuntu", "Ubuntu Sans"),
        FontOption("builtin:matrix_regular", "Matrix Sans Regular"),
        FontOption("builtin:matrix_print", "Matrix Sans Print"),
        FontOption("builtin:matrix_screen", "Matrix Sans Screen"),
        FontOption("builtin:matrix_video", "Matrix Sans Video"),
    )

    private fun preferences(context: Context) =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private fun importedDirectory(context: Context) =
        File(context.filesDir, "fonts").apply { mkdirs() }

    fun selectedId(context: Context): String =
        preferences(context).getString(KEY_SELECTED, DEFAULT_ID) ?: DEFAULT_ID

    fun setSelected(context: Context, id: String) {
        preferences(context).edit().putString(KEY_SELECTED, id).apply()
    }

    fun listOptions(context: Context): List<FontOption> {
        val imported = importedDirectory(context)
            .listFiles()
            .orEmpty()
            .filter { it.isFile && it.extension.lowercase() in setOf("ttf", "otf") }
            .sortedBy { it.name.lowercase() }
            .map { FontOption("custom:${it.name}", it.nameWithoutExtension, true) }
        return builtInOptions + imported
    }

    fun importedOptions(context: Context): List<FontOption> =
        listOptions(context).filter { it.imported }

    fun selectedName(context: Context): String =
        listOptions(context).firstOrNull { it.id == selectedId(context) }?.name
            ?: builtInOptions.first().name

    fun importFont(context: Context, uri: Uri): Result<FontOption> = runCatching {
        val resolver = context.contentResolver
        val displayName = resolver.query(
            uri,
            arrayOf(OpenableColumns.DISPLAY_NAME),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        } ?: "Imported font.ttf"

        val suppliedExtension = displayName.substringAfterLast('.', "").lowercase()
        val extension = when {
            suppliedExtension in setOf("ttf", "otf") -> suppliedExtension
            resolver.getType(uri)?.contains("opentype", ignoreCase = true) == true -> "otf"
            else -> "ttf"
        }

        val rawBase = if (suppliedExtension in setOf("ttf", "otf")) {
            displayName.substringBeforeLast('.')
        } else displayName
        val safeBase = rawBase
            .replace(Regex("[^A-Za-z0-9._ -]"), "_")
            .trim()
            .ifBlank { "Imported font" }

        val directory = importedDirectory(context)
        var destination = File(directory, "$safeBase.$extension")
        var counter = 2
        while (destination.exists()) {
            destination = File(directory, "$safeBase ($counter).$extension")
            counter += 1
        }

        resolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "Couldn't read that file." }
            destination.outputStream().use { output -> input.copyTo(output) }
        }

        try {
            Typeface.createFromFile(destination)
        } catch (error: Throwable) {
            destination.delete()
            throw IllegalArgumentException("That file is not a valid TTF or OTF font.", error)
        }

        val option = FontOption(
            id = "custom:${destination.name}",
            name = destination.nameWithoutExtension,
            imported = true,
        )
        setSelected(context, option.id)
        option
    }

    fun deleteFont(context: Context, id: String): Boolean {
        if (!id.startsWith("custom:")) return false
        val fileName = id.removePrefix("custom:")
        val deleted = File(importedDirectory(context), fileName).delete()
        if (selectedId(context) == id) setSelected(context, DEFAULT_ID)
        return deleted
    }

    private fun typeface(context: Context, id: String): Typeface {
        return when (id) {
            DEFAULT_ID -> Typeface.create("sans-serif-light", Typeface.NORMAL)
            "builtin:ubuntu" -> ResourcesCompat.getFont(context, R.font.ubuntu_sans_regular)
            "builtin:matrix_regular" -> ResourcesCompat.getFont(context, R.font.matrix_sans_regular)
            "builtin:matrix_print" -> ResourcesCompat.getFont(context, R.font.matrix_sans_print)
            "builtin:matrix_screen" -> ResourcesCompat.getFont(context, R.font.matrix_sans_screen)
            "builtin:matrix_video" -> ResourcesCompat.getFont(context, R.font.matrix_sans_video)
            else -> {
                if (id.startsWith("custom:")) {
                    val file = File(importedDirectory(context), id.removePrefix("custom:"))
                    if (file.exists()) {
                        try {
                            Typeface.createFromFile(file)
                        } catch (_: Throwable) {
                            Typeface.create("sans-serif-light", Typeface.NORMAL)
                        }
                    } else Typeface.create("sans-serif-light", Typeface.NORMAL)
                } else Typeface.create("sans-serif-light", Typeface.NORMAL)
            }
        } ?: Typeface.create("sans-serif-light", Typeface.NORMAL)
    }

    fun install(activity: FragmentActivity, activityRoot: View) {
        attach(activityRoot)
        activity.supportFragmentManager.registerFragmentLifecycleCallbacks(
            object : FragmentManager.FragmentLifecycleCallbacks() {
                override fun onFragmentViewCreated(
                    fm: FragmentManager,
                    fragment: Fragment,
                    view: View,
                    savedInstanceState: Bundle?,
                ) {
                    attach(view)
                }
            },
            true,
        )
    }

    fun attach(root: View) {
        root.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ ->
            applyToTree(root)
        }
        applyToTree(root)
    }

    fun applyToTree(root: View) {
        val id = selectedId(root.context)
        val fileStamp = if (id.startsWith("custom:")) {
            File(importedDirectory(root.context), id.removePrefix("custom:")).lastModified()
        } else 0L
        val signature = "$id:$fileStamp"
        applyRecursively(root, typeface(root.context, id), signature)
    }

    private fun applyRecursively(view: View, baseTypeface: Typeface, signature: String) {
        if (view is TextView && view.getTag(R.id.font_applied_tag) != signature) {
            val style = view.typeface?.style ?: Typeface.NORMAL
            view.typeface = Typeface.create(baseTypeface, style)
            view.setTag(R.id.font_applied_tag, signature)
        }
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                applyRecursively(view.getChildAt(index), baseTypeface, signature)
            }
        }
    }
}
