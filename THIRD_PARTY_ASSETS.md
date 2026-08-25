# Third-party visual assets

The storefront keeps fonts and icons local so production rendering does not
depend on a CDN.

- **IBM Plex Sans Arabic** — regular, medium, semibold, and bold WOFF2 files
  from the official IBM Plex repository. Licensed under the SIL Open Font
  License 1.1; the license is stored beside the font files in
  `static/fonts/ibm-plex-sans-arabic/LICENSE.txt`.
- **Cairo** — variable Arabic and Latin WOFF2 subsets from Google Fonts. Licensed
  under the SIL Open Font License 1.1; the license is stored beside the font
  files in `static/fonts/cairo/LICENSE.txt`.
- **Lucide Icons** — selected SVG source files from the official Lucide
  repository. Licensed under ISC, with some Feather-derived icons under MIT;
  the complete notice is stored in `core/icon_assets/LICENSE`.
- **Simple Icons** — WhatsApp, Instagram, Facebook, and TikTok marks from the
  official Simple Icons repository. Licensed CC0 1.0; the license is stored in
  `core/icon_assets/SIMPLE-ICONS-LICENSE.md`. Brand marks remain trademarks of
  their respective owners.

The Django tags `{% icon "name" %}` and `{% brand_icon "name" %}` inline the
vetted local SVG bodies with decorative accessibility attributes. Icon-only
controls provide their accessible names on the surrounding button or link.
