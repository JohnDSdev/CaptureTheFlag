from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path("olauncher")
android_ns = "http://schemas.android.com/apk/res/android"
tools_ns = "http://schemas.android.com/tools"
ET.register_namespace("android", android_ns)
ET.register_namespace("tools", tools_ns)
aid = lambda name: f"{{{android_ns}}}{name}"

# Add a font row immediately after the existing text-size row.
layout_path = root / "app/src/main/res/layout/fragment_settings.xml"
tree = ET.parse(layout_path)
xml_root = tree.getroot()
inserted = False
for parent in xml_root.iter():
    children = list(parent)
    for index, child in enumerate(children):
        contains_text_size = any(
            node.attrib.get(aid("id")) == "@+id/textSizeValue"
            for node in child.iter()
        )
        if not contains_text_size:
            continue

        frame = ET.Element(
            "FrameLayout",
            {
                aid("layout_width"): "match_parent",
                aid("layout_height"): "wrap_content",
                aid("layout_marginTop"): "12dp",
            },
        )
        ET.SubElement(
            frame,
            "TextView",
            {
                "style": "@style/TextSmall",
                aid("layout_width"): "wrap_content",
                aid("layout_height"): "wrap_content",
                aid("layout_marginStart"): "8dp",
                aid("paddingVertical"): "8dp",
                aid("text"): "@string/font_choice",
                aid("textColor"): "?attr/primaryColor",
            },
        )
        ET.SubElement(
            frame,
            "TextView",
            {
                aid("id"): "@+id/fontValue",
                "style": "@style/TextSmallBold",
                aid("layout_width"): "wrap_content",
                aid("layout_height"): "wrap_content",
                aid("layout_gravity"): "end|bottom",
                aid("layout_marginEnd"): "4dp",
                aid("padding"): "8dp",
                aid("text"): "@string/olauncher_default_font",
            },
        )
        parent.insert(index + 1, frame)
        inserted = True
        break
    if inserted:
        break

if not inserted:
    raise SystemExit("Could not find text-size row in fragment_settings.xml")
tree.write(layout_path, encoding="utf-8", xml_declaration=True)

# Strings and fork identity.
strings_path = root / "app/src/main/res/values/strings.xml"
strings = strings_path.read_text()
strings = re.sub(
    r'(<string\s+name="app_name"[^>]*>).*?(</string>)',
    r"\1Olauncher Fonts\2",
    strings,
    count=1,
)
additions = """
    <string name="font_choice">Font</string>
    <string name="olauncher_default_font">Olauncher default</string>
    <string name="add_font_file">Add font file…</string>
    <string name="remove_imported_font">Remove imported font…</string>
    <string name="font_added">Added %1$s</string>
    <string name="font_removed">Removed %1$s</string>
    <string name="font_import_failed">Could not add font: %1$s</string>
"""
strings = strings.replace("</resources>", additions + "</resources>")
strings_path.write_text(strings)

gradle_path = root / "app/build.gradle"
gradle = gradle_path.read_text()
gradle = gradle.replace(
    'applicationId "app.olauncher"',
    'applicationId "app.olauncher.fontpicker"',
)
gradle = gradle.replace(
    'versionName "v6.7.1"',
    'versionName "v6.7.1-fonts1"',
)
gradle_path.write_text(gradle)

# Install FontManager at the activity level.
main_path = root / "app/src/main/java/app/olauncher/MainActivity.kt"
main = main_path.read_text()
main = main.replace(
    "import app.olauncher.helper.getColorFromAttr",
    "import app.olauncher.helper.FontManager\nimport app.olauncher.helper.getColorFromAttr",
    1,
)
main = main.replace(
    "        setContentView(binding.root)\n",
    "        setContentView(binding.root)\n        FontManager.install(this, binding.root)\n",
    1,
)
main_path.write_text(main)

# Add the picker UI and imported-font workflow to SettingsFragment.
settings_path = root / "app/src/main/java/app/olauncher/ui/SettingsFragment.kt"
settings = settings_path.read_text()
settings = settings.replace(
    "import androidx.appcompat.app.AppCompatDelegate",
    "import androidx.activity.result.contract.ActivityResultContracts\n"
    "import androidx.appcompat.app.AlertDialog\n"
    "import androidx.appcompat.app.AppCompatDelegate",
    1,
)
settings = settings.replace(
    "import app.olauncher.helper.animateAlpha",
    "import app.olauncher.helper.FontManager\nimport app.olauncher.helper.animateAlpha",
    1,
)

property_anchor = "    private var showInstagram = false\n"
property_code = """    private var showInstagram = false

    private val fontFilePicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@registerForActivityResult
        FontManager.importFont(requireContext(), uri)
            .onSuccess { option ->
                requireContext().showToast(getString(R.string.font_added, option.name))
                requireActivity().recreate()
            }
            .onFailure { error ->
                requireContext().showToast(
                    getString(R.string.font_import_failed, error.message ?: "Unknown error")
                )
            }
    }
"""
if property_anchor not in settings:
    raise SystemExit("SettingsFragment property anchor not found")
settings = settings.replace(property_anchor, property_code, 1)

settings = settings.replace(
    "        populateTextSize()\n",
    "        populateTextSize()\n        populateFontText()\n",
    1,
)
settings = settings.replace(
    "            R.id.textSizeValue -> binding.textSizesLayout.visibility = View.VISIBLE\n",
    "            R.id.textSizeValue -> binding.textSizesLayout.visibility = View.VISIBLE\n"
    "            R.id.fontValue -> showFontPicker()\n",
    1,
)
settings = settings.replace(
    "        binding.textSizeValue.setOnClickListener(this)\n",
    "        binding.textSizeValue.setOnClickListener(this)\n"
    "        binding.fontValue.setOnClickListener(this)\n",
    1,
)

methods = """

    private fun populateFontText() {
        binding.fontValue.text = FontManager.selectedName(requireContext())
    }

    private fun showFontPicker() {
        val context = requireContext()
        val options = FontManager.listOptions(context)
        val importedFontsExist = options.any { it.imported }
        val labels = options.map { option ->
            if (option.id == FontManager.selectedId(context)) "✓ ${option.name}" else option.name
        }.toMutableList().apply {
            add(getString(R.string.add_font_file))
            if (importedFontsExist) add(getString(R.string.remove_imported_font))
        }

        val dialog = AlertDialog.Builder(context)
            .setTitle(R.string.font_choice)
            .setItems(labels.toTypedArray()) { _, which ->
                when {
                    which < options.size -> {
                        FontManager.setSelected(context, options[which].id)
                        requireActivity().recreate()
                    }
                    which == options.size -> fontFilePicker.launch(arrayOf("*/*"))
                    else -> showRemoveImportedFontDialog()
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .create()
        dialog.setOnShowListener {
            dialog.window?.decorView?.let(FontManager::applyToTree)
        }
        dialog.show()
    }

    private fun showRemoveImportedFontDialog() {
        val context = requireContext()
        val imported = FontManager.importedOptions(context)
        if (imported.isEmpty()) return

        val dialog = AlertDialog.Builder(context)
            .setTitle(R.string.remove_imported_font)
            .setItems(imported.map { it.name }.toTypedArray()) { _, which ->
                val option = imported[which]
                if (FontManager.deleteFont(context, option.id)) {
                    context.showToast(getString(R.string.font_removed, option.name))
                    requireActivity().recreate()
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .create()
        dialog.setOnShowListener {
            dialog.window?.decorView?.let(FontManager::applyToTree)
        }
        dialog.show()
    }
"""
last_brace = settings.rfind("}")
if last_brace == -1:
    raise SystemExit("SettingsFragment closing brace not found")
settings = settings[:last_brace] + methods + "\n" + settings[last_brace:]
settings_path.write_text(settings)
