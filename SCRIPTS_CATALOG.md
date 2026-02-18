# Script Catalog

Generated at: 2025-12-23 17:26

| File | Path (from root) | Category | Description |
|------|-------------------|----------|-------------|
| **add_media_to_products.py** | $escapedPath | Scratchpad | """ Р”РѕР±Р°РІР»РµРЅРёРµ РјРµРґРёР° (С„РѕС‚Рѕ) Рє С‚РѕРІР°СЂР°Рј С‡РµСЂРµР· Media API РСЃРїРѕР»СЊР·СѓРµС‚ Р·РѕР»РѕС‚РѕР№ СЃС‚Р°РЅРґР°СЂС‚ Shopware: POST /ap... |
| **add_ssh_key.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """Р”РѕР±Р°РІР»РµРЅРёРµ SSH РєР»СЋС‡Р° РЅР° СЃРµСЂРІРµСЂ""" |
| **analyze_pdf_structure.py** | $escapedPath | Scratchpad | import pdfplumber import re import sys |
| **apply_ru_settings.sh** | $escapedPath | Scratchpad | #!/bin/bash RU_LANG_ID=0xEC36B1EBDE6F11F0BB1BB0B33907AF53 RU_SNIPPET_SET_ID=0xEC4378A1DE6F11F0BB1BB0B33907AF53 |
| **architecture-diagnostic.ps1** | $escapedPath | Scratchpad | # Comprehensive Architecture Diagnostic Script # РџСЂРѕРІРµСЂРєР° РёРґРµР°Р»СЊРЅРѕР№ Р°СЂС…РёС‚РµРєС‚СѓСЂС‹ РїРµСЂРµРґР°С‡Рё РґР°РЅРЅС‹С… $ErrorActionPrefere... |
| **build_decision_matrix.py** | $escapedPath | Scratchpad | import math from pathlib import Path from typing import Dict, List |
| **bulk_update_all_products.py** | $escapedPath | Scratchpad | """ РњР°СЃСЃРѕРІРѕРµ РѕР±РЅРѕРІР»РµРЅРёРµ РІСЃРµС… С‚РѕРІР°СЂРѕРІ: РєР°С‚РµРіРѕСЂРёРё, properties, visibilities """ |
| **calc_residual_values.py** | $escapedPath | Scratchpad | import math from pathlib import Path from typing import Dict, List |
| **check_all_settings.py** | $escapedPath | Scratchpad | """ РџРѕР»РЅР°СЏ РїСЂРѕРІРµСЂРєР° РЅР°СЃС‚СЂРѕРµРє Shopware: СЏР·С‹РєРё, РІР°Р»СЋС‚С‹, Sales Channels """ |
| **check_all_sizes.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° РІСЃРµС… thumbnail sizes""" import paramiko ssh = paramiko.SSHClient() |
| **check_cat_trans.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SELECT HEX(language_id), name FROM category_translation WHERE name = 'ROOT_NAV' OR name = 'РљР°С‚Р°Р»РѕРі' LIMIT 10;" |
| **check_categories_and_media.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РєР°С‚РµРіРѕСЂРёР№ Рё РјРµРґРёР° РґР»СЏ СЃРѕР·РґР°РЅРЅС‹С… С‚РѕРІР°СЂРѕРІ. """ |
| **check_csv_fields.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° РїРѕР»РµР№ РІ СЃРіРµРЅРµСЂРёСЂРѕРІР°РЅРЅРѕРј CSV""" import csv from pathlib import Path |
| **check_currencies_after_deletion.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІР°Р»СЋС‚ РІ Shopware РїРѕСЃР»Рµ СѓРґР°Р»РµРЅРёСЏ Р»РёС€РЅРёС… РІР°Р»СЋС‚ """ |
| **check_currency.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІР°Р»СЋС‚ РІ Shopware """ |
| **check_currency_iso.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° ISO РєРѕРґР° СЃРёСЃС‚РµРјРЅРѕР№ РІР°Р»СЋС‚С‹ """ |
| **check_docker.py** | $escapedPath | Scratchpad | """ Remote Docker status checker for VPS-2 (77.233.222.214). Uses Paramiko with password auth to execute `docker ps`. |
| **check_domain.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SELECT HEX(id), url, HEX(language_id), HEX(snippet_set_id) FROM sales_channel_domain WHERE url LIKE '%dev.bireta.ru%';" |
| **check_eur_currency.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР°, РјРѕР¶РµС‚ Р»Рё Shopware РЅР°Р№С‚Рё РІР°Р»СЋС‚Сѓ РїРѕ ISO РєРѕРґСѓ EUR """ |
| **check_existing_products_currency.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІР°Р»СЋС‚С‹ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… С‚РѕРІР°СЂРѕРІ """ |
| **check_maincategory_api.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° API РґР»СЏ mainCategory""" import sys from pathlib import Path |
| **check_media_commands.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅС‹С… РєРѕРјР°РЅРґ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ media """ |
| **check_media_db.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° СЃРѕСЃС‚РѕСЏРЅРёСЏ media РІ Р±Р°Р·Рµ РґР°РЅРЅС‹С… """ |
| **check_media_details.py** | $escapedPath | Scratchpad | """ Р”РµС‚Р°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° РјРµРґРёР° РґР»СЏ РїРѕРЅРёРјР°РЅРёСЏ, РїРѕС‡РµРјСѓ РѕРЅРё РїСЂРѕРїСѓСЃРєР°СЋС‚СЃСЏ """ |
| **check_media_direct.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РјРµРґРёР° РЅР°РїСЂСЏРјСѓСЋ С‡РµСЂРµР· coverId """ |
| **check_media_relationships.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° СЃРІСЏР·РµР№ РјРµРґРёР° СЃ С‚РѕРІР°СЂР°РјРё С‡РµСЂРµР· product-media """ |
| **check_media_state.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° СЃРѕСЃС‚РѕСЏРЅРёСЏ media (РЅРµ thumbnail sizes) """ |
| **check_media_status.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° РјРµРґРёР° Сѓ С‚РѕРІР°СЂРѕРІ """ |
| **check_media_type_status.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° media_type РґР»СЏ РјРµРґРёР°""" import paramiko import sys |
| **check_new_products.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° СЃРѕР·РґР°РЅРЅС‹С… С‚РѕРІР°СЂРѕРІ Рё РёС… visibilities. """ |
| **check_original_template.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° РѕСЂРёРіРёРЅР°Р»СЊРЅРѕРіРѕ С€Р°Р±Р»РѕРЅР° Shopware""" |
| **check_outputs.py** | $escapedPath | Scratchpad | from pathlib import Path import pandas as pd BASE = Path(r"C:\cursor_project\biretos-automation\downloads") |
| **check_plugin_status.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° РїР»Р°РіРёРЅРѕРІ Shopware""" |
| **check_plugin_template.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° С€Р°Р±Р»РѕРЅР° РїР»Р°РіРёРЅР° РЅР° СЃРµСЂРІРµСЂРµ""" |
| **check_product_images_detailed.py** | $escapedPath | Scratchpad | """ Р”РµС‚Р°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° РёР·РѕР±СЂР°Р¶РµРЅРёР№ С‚РѕРІР°СЂРѕРІ Рё РёС… РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ. """ |
| **check_product_structure.py** | $escapedPath | Scratchpad | """Р’СЂРµРјРµРЅРЅС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РїСЂРѕРІРµСЂРєРё СЃС‚СЂСѓРєС‚СѓСЂС‹ С‚Р°Р±Р»РёС†С‹ product""" import paramiko ssh = paramiko.SSHClient() |
| **check_products_direct.py** | $escapedPath | Scratchpad | """ РџСЂСЏРјР°СЏ РїСЂРѕРІРµСЂРєР° С‚РѕРІР°СЂРѕРІ РІ Shopware С‡РµСЂРµР· GET Р·Р°РїСЂРѕСЃ """ |
| **check_products_direct_get.py** | $escapedPath | Scratchpad | """ РџСЂСЏРјР°СЏ РїСЂРѕРІРµСЂРєР° С‚РѕРІР°СЂРѕРІ С‡РµСЂРµР· GET Р·Р°РїСЂРѕСЃ """ |
| **check_products_visibility.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІРёРґРёРјРѕСЃС‚Рё С‚РѕРІР°СЂРѕРІ РЅР° С„СЂРѕРЅС‚РµРЅРґРµ Рё РЅР°Р»РёС‡РёСЏ С„РѕС‚Рѕ """ |
| **check_properties_presence.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° РЅР°Р»РёС‡РёСЏ РѕРїСЂРµРґРµР»С‘РЅРЅС‹С… С…Р°СЂР°РєС‚РµСЂРёСЃС‚РёРє РЅР° РІРёС‚СЂРёРЅРµ""" |
| **check_root_id.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SELECT HEX(id) FROM category WHERE HEX(id) = '019B141F60007EEFA571A533DDC98797';" |
| **check_ru.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SELECT HEX(id), code FROM locale WHERE code = 'ru-RU';" mysql -D shopware -e "SELECT HEX(id), name FROM language WHERE name... |
| **check_rub_currency.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІР°Р»СЋС‚С‹ RUB РІ Shopware РїРѕСЃР»Рµ РЅР°СЃС‚СЂРѕР№РєРё РІ Р°РґРјРёРЅ-РїР°РЅРµР»Рё """ |
| **check_rub_currency_full.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІР°Р»СЋС‚С‹ RUB СЃ РїРѕР»РЅРѕР№ РёРЅС„РѕСЂРјР°С†РёРµР№ С‡РµСЂРµР· search API """ |
| **check_sales_channel_currency_iso.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° ISO РєРѕРґР° РІР°Р»СЋС‚С‹ РёР· Sales Channel """ |
| **check_sales_channels_currency.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РІР°Р»СЋС‚С‹ РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ РІ Sales Channels """ |
| **check_sales_channels_detailed.py** | $escapedPath | Scratchpad | """ Р”РµС‚Р°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° Sales Channels С‡РµСЂРµР· GET API """ |
| **check_shopware_logs.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° Р»РѕРіРѕРІ Shopware РЅР° РѕС€РёР±РєРё""" |
| **check_shopware_media_config.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РЅР°СЃС‚СЂРѕРµРє РјРµРґРёР° РІ Shopware Рё Р°Р»СЊС‚РµСЂРЅР°С‚РёРІРЅС‹Рµ СЃРїРѕСЃРѕР±С‹ РіРµРЅРµСЂР°С†РёРё """ |
| **check_site_status.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° СЃС‚Р°С‚СѓСЃР° СЃР°Р№С‚Р°""" |
| **check_snippets.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SELECT translation_key, value FROM snippet WHERE HEX(snippet_set_id) = 'EC4378A1DE6F11F0BB1BB0B33907AF53' LIMIT 5;" |
| **check_storefront_context.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° storefront-РєРѕРЅС‚РµРєСЃС‚Р° РґР»СЏ РіРµРЅРµСЂР°С†РёРё thumbnails """ |
| **check_system_currency_details.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РґРµС‚Р°Р»РµР№ СЃРёСЃС‚РµРјРЅРѕР№ РІР°Р»СЋС‚С‹ """ |
| **check_tables.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SHOW TABLES LIKE 'product%';" mysql -D shopware -e "SELECT id FROM product LIMIT 5;" |
| **check_theme_and_fix.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° С‚РµРјС‹ Рё РёСЃРїСЂР°РІР»РµРЅРёРµ С‡РµСЂРµР· theme override""" |
| **check_thumbnail_commands.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅС‹С… РєРѕРјР°РЅРґ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ thumbnail sizes """ |
| **check_thumbnail_config.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РєРѕРЅС„РёРіСѓСЂР°С†РёРё thumbnail РІ Shopware """ |
| **check_thumbnail_settings.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РЅР°СЃС‚СЂРѕРµРє thumbnail Рё Р°Р»СЊС‚РµСЂРЅР°С‚РёРІРЅР°СЏ РіРµРЅРµСЂР°С†РёСЏ """ |
| **check_thumbnails_on_disk.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° РЅР°Р»РёС‡РёСЏ thumbnails РЅР° РґРёСЃРєРµ """ |
| **check_usa_forward.sh** | $escapedPath | Scratchpad | #!/bin/bash set -euo pipefail echo "=== Forwarding status $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" |
| **check_visibility_direct.py** | $escapedPath | Scratchpad | """ РџСЂСЏРјР°СЏ РїСЂРѕРІРµСЂРєР° visibility С‡РµСЂРµР· GET /api/product-visibility/{id}. """ |
| **check_visibility_structure.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° СЃС‚СЂСѓРєС‚СѓСЂС‹ visibilities СЃ categoryId""" import sys from pathlib import Path |
| **check_wg.sh** | $escapedPath | Scratchpad | #!/bin/bash set -euo pipefail { |
| **check_why_skipped.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР°, РїРѕС‡РµРјСѓ Shopware РїСЂРѕРїСѓСЃРєР°РµС‚ РЅР°С€Рё РјРµРґРёР° """ |
| **check-hosts-network.ps1** | $escapedPath | Scratchpad | # Network connectivity check Write-Host "`n=== External IP ===" -ForegroundColor Cyan try { |
| **check-port-10808.ps1** | $escapedPath | Scratchpad | $conn = Get-NetTCPConnection -LocalPort 10808 -State Listen -ErrorAction SilentlyContinue if ($conn) {     Write-Host "Port 10808 is listening" |
| **Check-ShopwareEndpoint.ps1** | $escapedPath | Scratchpad | param(     [string]$Url = "https://shopware.biretos.ae" ) |
| **check-vps-routing.sh** | $escapedPath | Scratchpad | #!/bin/bash # VPS Routing Check Script echo "=== VPS Routing Diagnostics ===" |
| **clear_shopware_cache.py** | $escapedPath | Scratchpad | """ РћС‡РёСЃС‚РєР° РєРµС€Р° Shopware РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РёР·РјРµРЅРµРЅРёР№ РЅР° СЃР°Р№С‚Рµ. """ |
| **clear_shopware_cache_aggressive.py** | $escapedPath | Scratchpad | """ РђРіСЂРµСЃСЃРёРІРЅР°СЏ РѕС‡РёСЃС‚РєР° РєСЌС€Р° Shopware С‡РµСЂРµР· РєРѕРЅСЃРѕР»СЊРЅС‹Рµ РєРѕРјР°РЅРґС‹ """ |
| **create_thumbnail_size_table.py** | $escapedPath | Scratchpad | """РЎРѕР·РґР°РЅРёРµ С‚Р°Р±Р»РёС†С‹ thumbnail_size СЃ РїСЂР°РІРёР»СЊРЅРѕР№ СЃС‚СЂСѓРєС‚СѓСЂРѕР№ Shopware""" import paramiko host = "77.233.222.214" |
| **create_thumbnail_sizes_api.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes С‡РµСЂРµР· Shopware API """ |
| **create_thumbnail_sizes_final.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes РґР»СЏ Shopware. """ |
| **create_thumbnail_sizes_single_sql.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes С‡РµСЂРµР· РѕРґРёРЅ SQL Р·Р°РїСЂРѕСЃ. """ |
| **create_thumbnails_direct_sql.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes РЅР°РїСЂСЏРјСѓСЋ С‡РµСЂРµР· SQL РєРѕРјР°РЅРґС‹. """ |
| **create_thumbnails_step_by_step.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes РїРѕС€Р°РіРѕРІРѕ. """ |
| **create_thumbnails_via_file.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes С‡РµСЂРµР· SQL С„Р°Р№Р» РЅР° СЃРµСЂРІРµСЂРµ. """ |
| **create_xray_shortcut.ps1** | $escapedPath | Scratchpad | $shell = New-Object -ComObject WScript.Shell $shortcutPath = 'C:\Users\Eugene\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\Xray.lnk' $shortc... |
| **deactivate_hide_properties_plugin.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """Р”РµР°РєС‚РёРІР°С†РёСЏ РїР»Р°РіРёРЅР° HideUnwantedProperties Рё РѕС‡РёСЃС‚РєР° РєРµС€Р°""" |
| **debug_categories_api.py** | $escapedPath | Scratchpad | """ РћС‚Р»Р°РґРєР°: РїСЂРѕРІРµСЂРєР° РєР°С‚РµРіРѕСЂРёР№ С‡РµСЂРµР· API. """ |
| **debug_enrich.py** | $escapedPath | Scratchpad | import sys from pathlib import Path sys.path.append(str(Path("_scratchpad").resolve())) |
| **debug_maincategory.py** | $escapedPath | Scratchpad | """РћС‚Р»Р°РґРєР° mainCategoryId""" import sys from pathlib import Path |
| **debug_maincategory2.py** | $escapedPath | Scratchpad | """РћС‚Р»Р°РґРєР° mainCategoryId - РїСЂРѕРІРµСЂРєР° РєР°С‚РµРіРѕСЂРёРё""" import sys from pathlib import Path |
| **debug_maincategory3.py** | $escapedPath | Scratchpad | """РћС‚Р»Р°РґРєР° mainCategoryId - РїСЂРѕРІРµСЂРєР° РѕС‚РІРµС‚Р° API""" import sys from pathlib import Path |
| **debug_pdf_columns.py** | $escapedPath | Scratchpad | import pdfplumber import sys import io |
| **debug_property_presence.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import requests |
| **debug_template_loading.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РћС‚Р»Р°РґРєР° Р·Р°РіСЂСѓР·РєРё С€Р°Р±Р»РѕРЅР°""" |
| **debug_thumbnails_issue.py** | $escapedPath | Scratchpad | """ Р”РёР°РіРЅРѕСЃС‚РёРєР° РїСЂРѕР±Р»РµРјС‹ СЃ thumbnails. """ |
| **debug_visibility_update.py** | $escapedPath | Scratchpad | """РћС‚Р»Р°РґРєР° РѕР±РЅРѕРІР»РµРЅРёСЏ visibility""" import sys from pathlib import Path |
| **deep_check_media.py** | $escapedPath | Scratchpad | """ Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° РјРµРґРёР° - РїРѕС‡РµРјСѓ Shopware РїСЂРѕРїСѓСЃРєР°РµС‚ """ |
| **diag_tbank_curl.sh** | $escapedPath | Scratchpad | #!/bin/bash set -euo pipefail ENV_FILE="/root/tbank-env" |
| **diagnose_cover_integrity.py** | $escapedPath | Scratchpad | """ Р”РёР°РіРЅРѕСЃС‚РёРєР° С†РµР»РѕСЃС‚РЅРѕСЃС‚Рё СЃРІСЏР·РµР№ coverId -> product_media. РџСЂРѕРІРµСЂСЏРµС‚, РїСЂР°РІРёР»СЊРЅРѕ Р»Рё СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹ c... |
| **diagnose_media_issue.py** | $escapedPath | Scratchpad | """ Р”РёР°РіРЅРѕСЃС‚РёРєР° РїСЂРѕР±Р»РµРјС‹ СЃ РїСЂРёРІСЏР·РєРѕР№ РјРµРґРёР° Рє С‚РѕРІР°СЂР°Рј """ |
| **diagnose_thumbnail_skip.py** | $escapedPath | Scratchpad | """Р”РёР°РіРЅРѕСЃС‚РёРєР° РїСЂРѕРїСѓСЃРєР° thumbnails""" import paramiko import sys |
| **diagnose_thumbnails.py** | $escapedPath | Scratchpad | """ Р”РёР°РіРЅРѕСЃС‚РёРєР° РїСЂРѕР±Р»РµРјС‹ СЃ thumbnails. """ |
| **direct_db_fix.py** | $escapedPath | Scratchpad | """ РџСЂСЏРјРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ С‡РµСЂРµР· Р‘Р” - СЃР±СЂРѕСЃ СЃРѕСЃС‚РѕСЏРЅРёСЏ РјРµРґРёР° """ |
| **disable_rp_filter.sh** | $escapedPath | Scratchpad | #!/bin/bash set -euo pipefail CONF_PATH="/etc/sysctl.d/99-wireguard-forward.conf" |
| **disable-local-vpn.ps1** | $escapedPath | Scratchpad | # Part A: Local PC (Windows) - Disable WireGuard and Xray $ErrorActionPreference = 'Continue' $results = @() |
| **disable-vps-ru.sh** | $escapedPath | Scratchpad | #!/bin/bash # Part B: VPS RU (Moscow) - Disable WireGuard and Xray set -e |
| **disable-vps-usa.sh** | $escapedPath | Scratchpad | #!/bin/bash # Part C: VPS USA - Disable WireGuard set -e |
| **dump_properties_table.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 import requests URL = "https://dev.bireta.ru/2sht-Korpus-lampy-zelenoy-ABB-CL-100G-1SFA619402R1002/505559050" |
| **enable_ip_forward.sh** | $escapedPath | Scratchpad | #!/bin/bash # Ensure IP forwarding is enabled for WireGuard server. set -euo pipefail |
| **enrich_honeywell.py** | $escapedPath | Scratchpad | """ Pipeline for enriching Honeywell lots with pricing data. Changes v2: |
| **final_thumbnail_fix.py** | $escapedPath | Scratchpad | """ Р¤РёРЅР°Р»СЊРЅРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ thumbnails - РїСЂРѕРІРµСЂРєР° РІСЃРµС… РІР°СЂРёР°РЅС‚РѕРІ. """ |
| **final-architecture-check.ps1** | $escapedPath | Scratchpad | # Final Architecture Check After VPN Disable # Comprehensive verification of DIRECT architecture $ErrorActionPreference = 'Continue' |
| **find_default_currency.py** | $escapedPath | Scratchpad | """ РћРїСЂРµРґРµР»РµРЅРёРµ СЂРµР°Р»СЊРЅРѕР№ default currency РІ Shopware С‡РµСЂРµР· System Config Рё Sales Channel """ |
| **find_default_currency_by_factor.py** | $escapedPath | Scratchpad | """ РџРѕРёСЃРє РІР°Р»СЋС‚С‹ СЃ factor=1.0 (СЃРёСЃС‚РµРјРЅР°СЏ РІР°Р»СЋС‚Р°) """ |
| **find_mediatype_table.py** | $escapedPath | Scratchpad | """ РџРѕРёСЃРє РїСЂР°РІРёР»СЊРЅРѕР№ С‚Р°Р±Р»РёС†С‹ РґР»СЏ mediaType """ |
| **find_mysql_and_check.py** | $escapedPath | Scratchpad | """ РџРѕРёСЃРє MySQL РєРѕРЅС‚РµР№РЅРµСЂР° Рё РїСЂРѕРІРµСЂРєР° media """ |
| **find_root.sh** | $escapedPath | Scratchpad | #!/bin/bash mysql -D shopware -e "SELECT HEX(id), name FROM category_translation WHERE name = 'Home';" mysql -D shopware -e "SELECT HEX(id), parent_id FROM c... |
| **find_rub_by_iso.py** | $escapedPath | Scratchpad | """ РџРѕРёСЃРє РІР°Р»СЋС‚С‹ RUB РїРѕ ISO РєРѕРґСѓ С‡РµСЂРµР· search API """ |
| **fix_categoryId_via_visibility_endpoint.py** | $escapedPath | Scratchpad | """ РСЃРїСЂР°РІР»РµРЅРёРµ categoryId С‡РµСЂРµР· РѕС‚РґРµР»СЊРЅС‹Р№ endpoint /api/product-visibility/{id}. """ |
| **fix_composer_json.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РСЃРїСЂР°РІР»РµРЅРёРµ composer.json РїР»Р°РіРёРЅР°""" |
| **fix_cover_ids.py** | $escapedPath | Scratchpad | """ РњР°СЃСЃРѕРІРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ cover_id РґР»СЏ С‚РѕРІР°СЂРѕРІ. Р’РѕСЃСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ РєРѕСЂСЂРµРєС‚РЅС‹Рµ СЃРІСЏР·Рё product.cover_id -... |
| **fix_existing_products.py** | $escapedPath | Scratchpad | """ РЎРєСЂРёРїС‚ РґР»СЏ РёСЃРїСЂР°РІР»РµРЅРёСЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… С‚РѕРІР°СЂРѕРІ: РґРѕР±Р°РІР»РµРЅРёРµ С„РѕС‚Рѕ Рё РїСЂРёРІСЏР·РєРё Рє Sales Channel """ |
| **fix_mediatype_and_generate.py** | $escapedPath | Scratchpad | """ РРЎРџР РђР’Р›Р•РќРР•: РЈСЃС‚Р°РЅРѕРІРєР° mediaType Рё РіРµРЅРµСЂР°С†РёСЏ thumbnails """ |
| **fix_mediatype_blob.py** | $escapedPath | Scratchpad | """ РСЃРїСЂР°РІР»РµРЅРёРµ mediaType (С…СЂР°РЅРёС‚СЃСЏ РєР°Рє JSON РІ longblob) """ |
| **fix_mediatype_final.py** | $escapedPath | Scratchpad | """ Р¤РёРЅР°Р»СЊРЅРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ: СѓСЃС‚Р°РЅРѕРІРєР° mediaType Рё РіРµРЅРµСЂР°С†РёСЏ thumbnails """ |
| **fix_mediatype_via_db.py** | $escapedPath | Scratchpad | """ РСЃРїСЂР°РІР»РµРЅРёРµ mediaType С‡РµСЂРµР· Р‘Р” РЅР°РїСЂСЏРјСѓСЋ """ |
| **fix_plugin_registration.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РСЃРїСЂР°РІР»РµРЅРёРµ СЂРµРіРёСЃС‚СЂР°С†РёРё РїР»Р°РіРёРЅР°""" |
| **fix_product_covers.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° Рё СѓСЃС‚Р°РЅРѕРІРєР° cover images РґР»СЏ С‚РѕРІР°СЂРѕРІ. """ |
| **fix_products_by_get.py** | $escapedPath | Scratchpad | """ РСЃРїСЂР°РІР»РµРЅРёРµ С‚РѕРІР°СЂРѕРІ, РЅР°Р№РґРµРЅРЅС‹С… С‡РµСЂРµР· GET Р·Р°РїСЂРѕСЃ """ |
| **fix_properties_template.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РСЃРїСЂР°РІР»РµРЅРёРµ С€Р°Р±Р»РѕРЅР° РїР»Р°РіРёРЅР° HideUnwantedProperties""" |
| **fix_template_path.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РСЃРїСЂР°РІР»РµРЅРёРµ РїСѓС‚Рё С€Р°Р±Р»РѕРЅР° РґР»СЏ Shopware 6.7""" |
| **fix_thumbnail_sizes.py** | $escapedPath | Scratchpad | """РСЃРїСЂР°РІР»РµРЅРёРµ РїСЂРѕР±Р»РµРјС‹ СЃ thumbnail sizes РІ Shopware""" import paramiko import sys |
| **fix_thumbnail_sizes_api.py** | $escapedPath | Scratchpad | """РСЃРїСЂР°РІР»РµРЅРёРµ РїСЂРѕР±Р»РµРјС‹ СЃ thumbnail sizes С‡РµСЂРµР· Shopware API""" import sys from pathlib import Path |
| **fix_thumbnail_sizes_cli.py** | $escapedPath | Scratchpad | """РСЃРїСЂР°РІР»РµРЅРёРµ РїСЂРѕР±Р»РµРјС‹ СЃ thumbnail sizes С‡РµСЂРµР· РєРѕРЅСЃРѕР»СЊРЅС‹Рµ РєРѕРјР°РЅРґС‹""" import paramiko import sys |
| **fix_thumbnail_sizes_direct.py** | $escapedPath | Scratchpad | """ РЎРѕР·РґР°РЅРёРµ thumbnail sizes РЅР°РїСЂСЏРјСѓСЋ С‡РµСЂРµР· SQL. """ |
| **fix_thumbnails_complete.py** | $escapedPath | Scratchpad | """ РџРѕР»РЅРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ thumbnails: media types + РіРµРЅРµСЂР°С†РёСЏ. """ |
| **fix_thumbnails_final.py** | $escapedPath | Scratchpad | """Р¤РёРЅР°Р»СЊРЅРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ thumbnail sizes""" import paramiko import uuid |
| **force_create_thumbnails.py** | $escapedPath | Scratchpad | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅРѕРµ СЃРѕР·РґР°РЅРёРµ thumbnails С‡РµСЂРµР· РїСЂСЏРјРѕРµ РѕР±РЅРѕРІР»РµРЅРёРµ РјРµРґРёР° """ |
| **force_fix_thumbnails.py** | $escapedPath | Scratchpad | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ thumbnails - РІСЃРµ РІРѕР·РјРѕР¶РЅС‹Рµ РІР°СЂРёР°РЅС‚С‹. """ |
| **force_generate_thumbnails.py** | $escapedPath | Scratchpad | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅР°СЏ РіРµРЅРµСЂР°С†РёСЏ thumbnails СЃ СЂР°Р·Р»РёС‡РЅС‹РјРё РїР°СЂР°РјРµС‚СЂР°РјРё """ |
| **force_rebuild_product_media.py** | $escapedPath | Scratchpad | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅРѕРµ РїРµСЂРµСЃРѕР·РґР°РЅРёРµ СЃРІСЏР·РµР№ С‚РѕРІР°СЂРѕРІ СЃ РјРµРґРёР° РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РїСЂРµРІСЊСЋС€РµРє. """ |
| **force_reset_thumbnails.py** | $escapedPath | Scratchpad | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅС‹Р№ reset СЃРѕСЃС‚РѕСЏРЅРёСЏ media Рё РіРµРЅРµСЂР°С†РёСЏ thumbnails """ |
| **force_ru.py** | $escapedPath | Scratchpad | import sys from pathlib import Path sys.path.insert(0, str(Path.cwd() / "insales_to_shopware_migration" / "src")) |
| **gen_snippet_sql.py** | $escapedPath | Scratchpad | import json import uuid def json_to_sql(json_file, snippet_set_id_hex, output_file): |
| **generate_thumbnails.py** | $escapedPath | Scratchpad | """Р“РµРЅРµСЂР°С†РёСЏ thumbnails РґР»СЏ Shopware media""" import paramiko import sys |
| **generate_thumbnails_force.py** | $escapedPath | Scratchpad | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅР°СЏ РіРµРЅРµСЂР°С†РёСЏ thumbnails РґР»СЏ РјРµРґРёР° РІ Shopware """ |
| **generate_thumbnails_now.py** | $escapedPath | Scratchpad | """ Р“РµРЅРµСЂР°С†РёСЏ thumbnails РґР»СЏ РІСЃРµС… РјРµРґРёР°. """ |
| **get_currency_from_sales_channel.py** | $escapedPath | Scratchpad | """ РџРѕР»СѓС‡РµРЅРёРµ РІР°Р»СЋС‚С‹ РЅР°РїСЂСЏРјСѓСЋ РёР· Sales Channel """ |
| **get_sales_channel_currency.py** | $escapedPath | Scratchpad | """ РџРѕР»СѓС‡РµРЅРёРµ РІР°Р»СЋС‚С‹ РёР· Sales Channel """ |
| **get_sales_channel_currency_id.py** | $escapedPath | Scratchpad | """ РџРѕР»СѓС‡РµРЅРёРµ РІР°Р»СЋС‚С‹ РёР· Sales Channel """ |
| **Get-InsalesCount.ps1** | $escapedPath | Scratchpad | param(     [string]$Endpoint,     [string]$ApiKey, |
| **honeywell_quality_report.py** | $escapedPath | Scratchpad | import math from pathlib import Path from typing import Dict, List |
| **Insales-Inspect.ps1** | $escapedPath | Scratchpad | param(     [string]$Shop = "biretos.insales.ru",     [string]$ApiKey = "changeme", |
| **install_activate_plugin.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РЈСЃС‚Р°РЅРѕРІРєР° Рё Р°РєС‚РёРІР°С†РёСЏ РїР»Р°РіРёРЅР° HideUnwantedProperties""" |
| **install_docker.sh** | $escapedPath | Scratchpad | #!/usr/bin/env bash set -euo pipefail echo "[INFO] Installing Docker prerequisites..." |
| **install_python.ps1** | $escapedPath | Scratchpad | Set-StrictMode -Version Latest $ErrorActionPreference = 'Stop' $pythonVersion = '3.12.8' |
| **install_wireguard_tools.sh** | $escapedPath | Scratchpad | #!/bin/bash set -euo pipefail LOG_FILE="/tmp/install_wireguard_tools.log" |
| **keygen.sh** | $escapedPath | Scratchpad | #!/bin/bash # WireGuard key generation script # Safe for remote execution via Upload & Execute pattern |
| **latency_benchmark.sh** | $escapedPath | Scratchpad | #!/bin/bash # Measure latency to critical Cursor endpoints via WireGuard tunnel. set -euo pipefail |
| **parse_error.py** | $escapedPath | Scratchpad | import json import re with open(r'c:\Users\Eugene\.cursor\projects\c-cursor-project-biretos-automation\agent-tools\0f9b827e-69fc-4312-bf75-aad947d15d47.txt',... |
| **read_remote_file.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 import paramiko import sys |
| **rebind_product_media.py** | $escapedPath | Scratchpad | """ РџРµСЂРµРїСЂРёРІСЏР·РєР° РјРµРґРёР° Рє С‚РѕРІР°СЂР°Рј РґР»СЏ С‚СЂРёРіРіРµСЂР° РіРµРЅРµСЂР°С†РёРё thumbnails РЎРєСЂРёРїС‚ РїРµСЂРµРѕС‚РїСЂР°РІР»СЏРµС‚ СЃС... |
| **rebuild_storefront.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџРµСЂРµСЃР±РѕСЂРєР° storefront Shopware""" |
| **refresh_shopware_indexes.py** | $escapedPath | Scratchpad | """ РћР±РЅРѕРІР»РµРЅРёРµ РёРЅРґРµРєСЃРѕРІ Shopware РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РёР·РјРµРЅРµРЅРёР№ РЅР° СЃР°Р№С‚Рµ. """ |
| **remote_curl_test.sh** | $escapedPath | Scratchpad | #!/bin/bash # Run curl via Xray user to verify tunnel exit IP. set -euo pipefail |
| **remote_insales_inspect.sh** | $escapedPath | Scratchpad | #!/usr/bin/env bash set -euo pipefail SHOP="${1:-biretos.myinsales.ru}" |
| **remote_shopware_diag.sh** | $escapedPath | Scratchpad | #!/usr/bin/env bash set -euo pipefail report_section() { |
| **rename_cats.py** | $escapedPath | Scratchpad | import sys from pathlib import Path sys.path.insert(0, str(Path.cwd() / "insales_to_shopware_migration" / "src")) |
| **restart_php_fpm.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџРµСЂРµР·Р°РїСѓСЃРє PHP-FPM РґР»СЏ СЃР±СЂРѕСЃР° СЃРѕСЃС‚РѕСЏРЅРёСЏ""" |
| **restart_shopware_container.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџРµСЂРµР·Р°РїСѓСЃРє РєРѕРЅС‚РµР№РЅРµСЂР° Shopware""" |
| **restore_template_emergency.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РЎР РћР§РќРћР• РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ РѕСЂРёРіРёРЅР°Р»СЊРЅРѕРіРѕ С€Р°Р±Р»РѕРЅР° Shopware""" |
| **run_generate_csv_wrapper.py** | $escapedPath | Scratchpad | import sys from pathlib import Path ROOT = Path(__file__).resolve().parents[1] |
| **run_remote_command.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 import paramiko import sys |
| **set_sales_channel_currency.py** | $escapedPath | Scratchpad | """ РЈСЃС‚Р°РЅРѕРІРєР° РІР°Р»СЋС‚С‹ РІ Sales Channel С‡РµСЂРµР· API """ |
| **setup_ru_api.py** | $escapedPath | Scratchpad | import sys from pathlib import Path sys.path.insert(0, str(Path.cwd() / "insales_to_shopware_migration" / "src")) |
| **setup_ru_db.sh** | $escapedPath | Scratchpad | #!/bin/bash # IDs from previous check RU_LOCALE_ID=0x019A0C73DEBB73E483202B861AA4FE18 |
| **setup_ssh_key.py** | $escapedPath | Scratchpad | import argparse import os from pathlib import Path |
| **setup_thumbnail_sizes.py** | $escapedPath | Scratchpad | """РќР°СЃС‚СЂРѕР№РєР° thumbnail sizes РґР»СЏ Shopware""" import paramiko import sys |
| **Setup-SSHKey.ps1** | $escapedPath | Scratchpad | param(     [string]$TargetHost = "77.233.222.214",     [string]$User = "root", |
| **test_direct_visibility_update.py** | $escapedPath | Scratchpad | """РўРµСЃС‚ РїСЂСЏРјРѕРіРѕ РѕР±РЅРѕРІР»РµРЅРёСЏ visibility С‡РµСЂРµР· product-visibility endpoint""" import sys from pathlib import Path |
| **test_main_categories_endpoint.py** | $escapedPath | Scratchpad | """РўРµСЃС‚ СѓСЃС‚Р°РЅРѕРІРєРё mainCategory С‡РµСЂРµР· main-categories endpoint""" import sys from pathlib import Path |
| **test_maincategory_sync.py** | $escapedPath | Scratchpad | """РўРµСЃС‚ mainCategoryId С‡РµСЂРµР· Sync API""" import sys from pathlib import Path |
| **test_media_attachment.py** | $escapedPath | Scratchpad | """ РўРµСЃС‚РёСЂРѕРІР°РЅРёРµ РїСЂРёРІСЏР·РєРё РјРµРґРёР° Рє С‚РѕРІР°СЂСѓ СЃ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµРј СѓР¶Рµ СЃРѕР·РґР°РЅРЅРѕРіРѕ РјРµРґРёР° """ |
| **test_mysql_final.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """Р¤РёРЅР°Р»СЊРЅС‹Р№ С‚РµСЃС‚ non-interactive MySQL С‡РµСЂРµР· SSH""" |
| **test_new_product_rub.py** | $escapedPath | Scratchpad | """ РўРµСЃС‚ СЃРѕР·РґР°РЅРёСЏ РЅРѕРІРѕРіРѕ С‚РѕРІР°СЂР° РґР»СЏ РїСЂРѕРІРµСЂРєРё РІР°Р»СЋС‚С‹ RUB """ |
| **test_non_interactive_mysql.sh** | $escapedPath | Scratchpad | #!/usr/bin/env bash # РўРµСЃС‚ non-interactive MySQL РєРѕРјР°РЅРґС‹ SSH_HOST="root@216.9.227.124" |
| **test_query.py** | $escapedPath | Scratchpad | """РўРµСЃС‚РѕРІС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РїСЂРѕРІРµСЂРєРё SQL Р·Р°РїСЂРѕСЃР°""" import paramiko ssh = paramiko.SSHClient() |
| **test_sync_visibility.py** | $escapedPath | Scratchpad | """РўРµСЃС‚ РѕР±РЅРѕРІР»РµРЅРёСЏ visibility С‡РµСЂРµР· Sync API""" import sys from pathlib import Path |
| **test_visibility_update.py** | $escapedPath | Scratchpad | """РўРµСЃС‚ РѕР±РЅРѕРІР»РµРЅРёСЏ visibility СЃ categoryId""" import sys from pathlib import Path |
| **test_with_sales_channel.py** | $escapedPath | Scratchpad | """ РўРµСЃС‚ РёРјРїРѕСЂС‚Р° СЃ Sales Channel ID РІ Р·Р°РіРѕР»РѕРІРєР°С… """ |
| **test_with_sales_channel_header.py** | $escapedPath | Scratchpad | """ РўРµСЃС‚ РёРјРїРѕСЂС‚Р° СЃ Sales Channel ID РІ Р·Р°РіРѕР»РѕРІРєР°С… """ |
| **Test-InsalesRequest.ps1** | $escapedPath | Scratchpad | param(     [string]$Url,     [string]$ApiKey, |
| **Test-NonInteractiveMySQL.ps1** | $escapedPath | Scratchpad | # РўРµСЃС‚ non-interactive MySQL РєРѕРјР°РЅРґС‹ С‡РµСЂРµР· SSH $SSH_HOST = "root@216.9.227.124" $ENV_PATH = "/var/www/shopware/.env" |
| **test-rtt.ps1** | $escapedPath | Scratchpad | param($target, $name) Write-Host "Testing $name ($target)..." -ForegroundColor Cyan try { |
| **test-rtt-direct.ps1** | $escapedPath | Scratchpad | param($target, $name) Write-Host "Testing $name ($target)..." -ForegroundColor Cyan try { |
| **test-rtt-ping.ps1** | $escapedPath | Scratchpad | param($target, $name) Write-Host "Testing $name ($target)..." -ForegroundColor Cyan try { |
| **tunnel_health_check.sh** | $escapedPath | Scratchpad | #!/bin/bash set -euo pipefail LOG="/tmp/tunnel_health_check.log" |
| **update_all_media.py** | $escapedPath | Scratchpad | """ РћР±РЅРѕРІР»РµРЅРёРµ РІСЃРµС… РјРµРґРёР° РґР»СЏ С‚СЂРёРіРіРµСЂР° РіРµРЅРµСЂР°С†РёРё thumbnails """ |
| **update_domain.sh** | $escapedPath | Scratchpad | #!/usr/bin/env bash set -euo pipefail docker exec shopware bash -lc 'mysql -h 127.0.0.1 -u root -pshopware shopware -e "UPDATE sales_channel_domain SET url='... |
| **update_properties_template.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РћР±РЅРѕРІР»РµРЅРёРµ С€Р°Р±Р»РѕРЅР° РїР»Р°РіРёРЅР° HideUnwantedProperties РЅР° СЃРµСЂРІРµСЂРµ""" |
| **update_python_path.ps1** | $escapedPath | Scratchpad | Set-StrictMode -Version Latest $ErrorActionPreference = 'Stop' $pythonHome = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312' |
| **upload_snippets.py** | $escapedPath | Scratchpad | import sys from pathlib import Path sys.path.insert(0, str(Path.cwd() / "insales_to_shopware_migration" / "src")) |
| **validate_test_import.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР° С‚РµСЃС‚РѕРІРѕРіРѕ РёРјРїРѕСЂС‚Р° С‚РѕРІР°СЂРѕРІ РІ Shopware """ |
| **verify_categories_update.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР°, С‡С‚Рѕ РєР°С‚РµРіРѕСЂРёРё РїСЂР°РІРёР»СЊРЅРѕ РґРѕР±Р°РІР»РµРЅС‹ Рє С‚РѕРІР°СЂР°Рј. """ |
| **verify_category_update.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° РѕР±РЅРѕРІР»РµРЅРёСЏ РєР°С‚РµРіРѕСЂРёР№ Рё mainCategoryId""" import sys from pathlib import Path |
| **verify_maincategory_result.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° СЂРµР·СѓР»СЊС‚Р°С‚Р° РѕР±РЅРѕРІР»РµРЅРёСЏ mainCategory""" import sys from pathlib import Path |
| **verify_new_product_visibilities.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР°, С‡С‚Рѕ РїСЂРё СЃРѕР·РґР°РЅРёРё РЅРѕРІРѕРіРѕ С‚РѕРІР°СЂР° categoryId РєРѕСЂСЂРµРєС‚РЅРѕ СѓСЃС‚Р°РЅР°РІР»РёРІР°РµС‚СЃСЏ РІ visibilities. """ |
| **verify_plugin_structure.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° Рё РёСЃРїСЂР°РІР»РµРЅРёРµ СЃС‚СЂСѓРєС‚СѓСЂС‹ РїР»Р°РіРёРЅР°""" |
| **verify_properties_hidden.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР°, С‡С‚Рѕ РЅРµР¶РµР»Р°С‚РµР»СЊРЅС‹Рµ СЃРІРѕР№СЃС‚РІР° СЃРєСЂС‹С‚С‹ РЅР° СЃР°Р№С‚Рµ""" |
| **verify_rub_default.py** | $escapedPath | Scratchpad | """ РџСЂРѕРІРµСЂРєР°, С‡С‚Рѕ RUB СѓСЃС‚Р°РЅРѕРІР»РµРЅР° РєР°Рє СЃРёСЃС‚РµРјРЅР°СЏ РІР°Р»СЋС‚Р° """ |
| **verify_template_restored.py** | $escapedPath | Scratchpad | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРЅРѕРіРѕ С€Р°Р±Р»РѕРЅР°""" |
| **verify_thumbnail_sizes.py** | $escapedPath | Scratchpad | """РџСЂРѕРІРµСЂРєР° СЃРѕР·РґР°РЅРЅС‹С… thumbnail sizes""" import paramiko host = "77.233.222.214" |
| **__init__.py** | $escapedPath | Utilities | # Licensed under the Apache License, Version 2.0 (the "License"); # you may not use this file except in compliance with the License. # You may obtain a copy ... |
| **__init__.py** | $escapedPath | Utilities | from .core import contents, where __all__ = ["contents", "where"] __version__ = "2025.11.12" |
| **__main__.py** | $escapedPath | Utilities | import argparse from certifi import contents, where parser = argparse.ArgumentParser() |
| **core.py** | $escapedPath | Utilities | """ certifi.py ~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | __all__ = ['FFI', 'VerificationError', 'VerificationMissing', 'CDefError',            'FFIError'] from .api import FFI |
| **_imp_emulation.py** | $escapedPath | Utilities | try:     # this works on Python < 3.12     from imp import * |
| **_shimmed_dist_utils.py** | $escapedPath | Utilities | """ Temporary shim module to indirect the bits of distutils we need from setuptools/distutils while providing useful error messages beyond `No module named '... |
| **api.py** | $escapedPath | Utilities | import sys, types from .lock import allocate_lock from .error import CDefError |
| **backend_ctypes.py** | $escapedPath | Utilities | import ctypes, ctypes.util, operator, sys from . import model if sys.version_info < (3,): |
| **cffi_opcode.py** | $escapedPath | Utilities | from .error import VerificationError class CffiOp(object):     def __init__(self, op, arg): |
| **commontypes.py** | $escapedPath | Utilities | import sys from . import model from .error import FFIError |
| **cparser.py** | $escapedPath | Utilities | from . import model from .commontypes import COMMON_TYPES, resolve_common_type from .error import FFIError, CDefError |
| **error.py** | $escapedPath | Utilities | class FFIError(Exception):     __module__ = 'cffi' class CDefError(Exception): |
| **ffiplatform.py** | $escapedPath | Utilities | import sys, os from .error import VerificationError LIST_OF_FILE_NAMES = ['sources', 'include_dirs', 'library_dirs', |
| **lock.py** | $escapedPath | Utilities | import sys if sys.version_info < (3,):     try: |
| **model.py** | $escapedPath | Utilities | import types import weakref from .lock import allocate_lock |
| **pkgconfig.py** | $escapedPath | Utilities | # pkg-config, https://www.freedesktop.org/wiki/Software/pkg-config/ integration for cffi import sys, os, subprocess from .error import PkgConfigError |
| **recompiler.py** | $escapedPath | Utilities | import io, os, sys, sysconfig from . import ffiplatform, model from .error import VerificationError |
| **setuptools_ext.py** | $escapedPath | Utilities | import os import sys import sysconfig |
| **vengine_cpy.py** | $escapedPath | Utilities | # # DEPRECATED: implementation for ffi.verify() # |
| **vengine_gen.py** | $escapedPath | Utilities | # # DEPRECATED: implementation for ffi.verify() # |
| **verifier.py** | $escapedPath | Utilities | # # DEPRECATED: implementation for ffi.verify() # |
| **__init__.py** | $escapedPath | Utilities | """ Charset-Normalizer ~~~~~~~~~~~~~~ |
| **__main__.py** | $escapedPath | Utilities | from __future__ import annotations from .cli import cli_detect if __name__ == "__main__": |
| **api.py** | $escapedPath | Utilities | from __future__ import annotations import logging from os import PathLike |
| **cd.py** | $escapedPath | Utilities | from __future__ import annotations import importlib from codecs import IncrementalDecoder |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations from .__main__ import cli_detect, query_yes_no __all__ = ( |
| **__main__.py** | $escapedPath | Utilities | from __future__ import annotations import argparse import sys |
| **constant.py** | $escapedPath | Utilities | from __future__ import annotations from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE, BOM_UTF32_BE, BOM_UTF32_LE from encodings.aliases import aliases |
| **legacy.py** | $escapedPath | Utilities | from __future__ import annotations from typing import TYPE_CHECKING, Any from warnings import warn |
| **md.py** | $escapedPath | Utilities | from __future__ import annotations from functools import lru_cache from logging import getLogger |
| **models.py** | $escapedPath | Utilities | from __future__ import annotations from encodings.aliases import aliases from hashlib import sha256 |
| **utils.py** | $escapedPath | Utilities | from __future__ import annotations import importlib import logging |
| **version.py** | $escapedPath | Utilities | """ Expose version """ |
| **__about__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **exceptions.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **fernet.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_oid.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **asn1.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **backend.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_conditional.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **binding.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **algorithms.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_asymmetric.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_cipheralgorithm.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_serialization.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **dh.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **dsa.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **ec.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **ed25519.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **ed448.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **padding.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **rsa.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **types.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **utils.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **x25519.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **x448.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **aead.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **algorithms.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **base.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **modes.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **cmac.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **constant_time.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **hashes.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **hmac.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **argon2.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **concatkdf.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **hkdf.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **kbkdf.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **pbkdf2.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **scrypt.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **x963kdf.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **keywrap.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **padding.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **poly1305.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **base.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **pkcs12.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **pkcs7.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **ssh.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **hotp.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **totp.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **utils.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **base.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **certificate_transparency.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **extensions.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **general_name.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **name.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **ocsp.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **oid.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **verification.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | from .core import (     IDNABidiError,     IDNAError, |
| **codec.py** | $escapedPath | Utilities | import codecs import re from typing import Any, Optional, Tuple |
| **compat.py** | $escapedPath | Utilities | from typing import Any, Union from .core import decode, encode def ToASCII(label: str) -> bytes: |
| **core.py** | $escapedPath | Utilities | import bisect import re import unicodedata |
| **idnadata.py** | $escapedPath | Utilities | # This file is automatically generated by tools/idna-data __version__ = "16.0.0" scripts = { |
| **intranges.py** | $escapedPath | Utilities | """ Given a list of integers, made up of (hopefully) a small number of long runs of consecutive integers, compute a representation of the form |
| **package_data.py** | $escapedPath | Utilities | __version__ = "3.11" |
| **uts46data.py** | $escapedPath | Utilities | # This file is automatically generated by tools/idna-data # vim: set fileencoding=utf-8 : from typing import List, Tuple, Union |
| **__init__.py** | $escapedPath | Utilities | from typing import Any, Optional from ._version import __version_info__, __version__  # noqa from .collection import Collection  # noqa |
| **__main__.py** | $escapedPath | Utilities | from invoke.main import program program.run() |
| **_version.py** | $escapedPath | Utilities | __version_info__ = (2, 2, 1) __version__ = ".".join(map(str, __version_info__)) |
| **collection.py** | $escapedPath | Utilities | import copy from types import ModuleType from typing import Any, Callable, Dict, List, Optional, Tuple |
| **__init__.py** | $escapedPath | Utilities |  |
| **complete.py** | $escapedPath | Utilities | """ Command-line completion mechanisms, executed by the core ``--complete`` flag. """ |
| **config.py** | $escapedPath | Utilities | import copy import json import os |
| **context.py** | $escapedPath | Utilities | import os import re from contextlib import contextmanager |
| **env.py** | $escapedPath | Utilities | """ Environment variable configuration loading class. Using a class here doesn't really model anything but makes state passing (in a |
| **exceptions.py** | $escapedPath | Utilities | """ Custom exception classes. These vary in use case from "we needed a specific data structure layout in |
| **executor.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union from .config import Config from .parser import ParserContext |
| **loader.py** | $escapedPath | Utilities | import os import sys from importlib.machinery import ModuleSpec |
| **main.py** | $escapedPath | Utilities | """ Invoke's own 'binary' entrypoint. Dogfoods the `program` module. |
| **__init__.py** | $escapedPath | Utilities | # flake8: noqa from .parser import * from .context import ParserContext |
| **argument.py** | $escapedPath | Utilities | from typing import Any, Iterable, Optional, Tuple # TODO: dynamic type for kind # T = TypeVar('T') |
| **context.py** | $escapedPath | Utilities | import itertools from typing import Any, Dict, List, Iterable, Optional, Tuple, Union try: |
| **parser.py** | $escapedPath | Utilities | import copy from typing import TYPE_CHECKING, Any, Iterable, List, Optional try: |
| **program.py** | $escapedPath | Utilities | import getpass import inspect import json |
| **runners.py** | $escapedPath | Utilities | import errno import locale import os |
| **tasks.py** | $escapedPath | Utilities | """ This module contains the core `.Task` class & convenience decorators used to generate new tasks. |
| **terminals.py** | $escapedPath | Utilities | """ Utility functions surrounding terminal devices & I/O. Much of this code performs platform-sensitive branching, e.g. Windows support. |
| **util.py** | $escapedPath | Utilities | from collections import namedtuple from contextlib import contextmanager from types import TracebackType |
| **__init__.py** | $escapedPath | Utilities |  |
| **__init__.py** | $escapedPath | Utilities | from .machine import (StateMachine, state, transition,                                InvalidConfiguration, InvalidTransition,                               ... |
| **backwardscompat.py** | $escapedPath | Utilities | import sys if sys.version_info >= (3,):     def callable(obj): |
| **machine.py** | $escapedPath | Utilities | import re import inspect from .backwardscompat import callable |
| **__init__.py** | $escapedPath | Utilities | from ._version import __version_info__, __version__  # noqa from .attribute_dict import AttributeDict from .alias_dict import AliasDict |
| **_version.py** | $escapedPath | Utilities | __version_info__ = (2, 0, 1) __version__ = ".".join(map(str, __version_info__)) |
| **alias_dict.py** | $escapedPath | Utilities | class AliasDict(dict):     def __init__(self, *args, **kwargs):         super(AliasDict, self).__init__(*args, **kwargs) |
| **attribute_dict.py** | $escapedPath | Utilities | class AttributeDict(dict):     def __getattr__(self, key):         try: |
| **__init__.py** | $escapedPath | Utilities | from .error import * from .tokens import * from .events import * |
| **composer.py** | $escapedPath | Utilities | __all__ = ['Composer', 'ComposerError'] from .error import MarkedYAMLError from .events import * |
| **constructor.py** | $escapedPath | Utilities | __all__ = [     'BaseConstructor',     'SafeConstructor', |
| **cyaml.py** | $escapedPath | Utilities | __all__ = [     'CBaseLoader', 'CSafeLoader', 'CFullLoader', 'CUnsafeLoader', 'CLoader',     'CBaseDumper', 'CSafeDumper', 'CDumper' |
| **dumper.py** | $escapedPath | Utilities | __all__ = ['BaseDumper', 'SafeDumper', 'Dumper'] from .emitter import * from .serializer import * |
| **emitter.py** | $escapedPath | Utilities | # Emitter expects events obeying the following grammar: # stream ::= STREAM-START document* STREAM-END # document ::= DOCUMENT-START node DOCUMENT-END |
| **error.py** | $escapedPath | Utilities | __all__ = ['Mark', 'YAMLError', 'MarkedYAMLError'] class Mark:     def __init__(self, name, index, line, column, buffer, pointer): |
| **events.py** | $escapedPath | Utilities | # Abstract classes. class Event(object):     def __init__(self, start_mark=None, end_mark=None): |
| **loader.py** | $escapedPath | Utilities | __all__ = ['BaseLoader', 'FullLoader', 'SafeLoader', 'Loader', 'UnsafeLoader'] from .reader import * from .scanner import * |
| **nodes.py** | $escapedPath | Utilities | class Node(object):     def __init__(self, tag, value, start_mark, end_mark):         self.tag = tag |
| **parser.py** | $escapedPath | Utilities | # The following YAML grammar is LL(1) and is parsed by a recursive descent # parser. # |
| **reader.py** | $escapedPath | Utilities | # This module contains abstractions for the input stream. You don't have to # looks further, there are no pretty code. # |
| **representer.py** | $escapedPath | Utilities | __all__ = ['BaseRepresenter', 'SafeRepresenter', 'Representer',     'RepresenterError'] from .error import * |
| **resolver.py** | $escapedPath | Utilities | __all__ = ['BaseResolver', 'Resolver'] from .error import * from .nodes import * |
| **scanner.py** | $escapedPath | Utilities | # Scanner produces tokens of the following types: # STREAM-START # STREAM-END |
| **serializer.py** | $escapedPath | Utilities | __all__ = ['Serializer', 'SerializerError'] from .error import YAMLError from .events import * |
| **tokens.py** | $escapedPath | Utilities | class Token(object):     def __init__(self, start_mark, end_mark):         self.start_mark = start_mark |
| **watchers.py** | $escapedPath | Utilities | import re import threading from typing import Generator, Iterable |
| **__init__.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **__init__.py** | $escapedPath | Utilities | # Copyright 2013-2019 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_aead.py** | $escapedPath | Utilities | # Copyright 2017 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_box.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_core.py** | $escapedPath | Utilities | # Copyright 2018 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_generichash.py** | $escapedPath | Utilities | # Copyright 2013-2019 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_hash.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_kx.py** | $escapedPath | Utilities | # Copyright 2018 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_pwhash.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_scalarmult.py** | $escapedPath | Utilities | # Copyright 2013-2018 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_secretbox.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_secretstream.py** | $escapedPath | Utilities | # Copyright 2013-2018 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_shorthash.py** | $escapedPath | Utilities | # Copyright 2016 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **crypto_sign.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **randombytes.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **sodium_core.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **utils.py** | $escapedPath | Utilities | # Copyright 2013-2017 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **encoding.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **exceptions.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **hash.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **hashlib.py** | $escapedPath | Utilities | # Copyright 2016-2019 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **public.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **__init__.py** | $escapedPath | Utilities | # Copyright 2017 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **_argon2.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **argon2i.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **argon2id.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **scrypt.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **secret.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **signing.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **utils.py** | $escapedPath | Utilities | # Copyright 2013 Donald Stufft and individual contributors # # Licensed under the Apache License, Version 2.0 (the "License"); |
| **__init__.py** | $escapedPath | Utilities | # Copyright (C) 2003-2011  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **_winapi.py** | $escapedPath | Utilities | """ Windows API functions implemented as ctypes functions and classes as found in jaraco.windows (3.4.1). |
| **agent.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  John Rochester <john@jrochester.org> # # This file is part of paramiko. |
| **auth_handler.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **auth_strategy.py** | $escapedPath | Utilities | """ Modern, adaptable authentication machinery. Replaces certain parts of `.SSHClient`. For a concrete implementation, see the |
| **ber.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **buffered_pipe.py** | $escapedPath | Utilities | # Copyright (C) 2006-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **channel.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **client.py** | $escapedPath | Utilities | # Copyright (C) 2006-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **common.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **compress.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **config.py** | $escapedPath | Utilities | # Copyright (C) 2006-2007  Robey Pointer <robeypointer@gmail.com> # Copyright (C) 2012  Olle Lundberg <geek@nerd.sh> # |
| **ecdsakey.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **ed25519key.py** | $escapedPath | Utilities | # This file is part of paramiko. # # Paramiko is free software; you can redistribute it and/or modify it under the |
| **file.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **hostkeys.py** | $escapedPath | Utilities | # Copyright (C) 2006-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **kex_curve25519.py** | $escapedPath | Utilities | import binascii import hashlib from cryptography.exceptions import UnsupportedAlgorithm |
| **kex_ecdh_nist.py** | $escapedPath | Utilities | """ Ephemeral Elliptic Curve Diffie-Hellman (ECDH) key exchange RFC 5656, Section 4 |
| **kex_gex.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **kex_group1.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **kex_group14.py** | $escapedPath | Utilities | # Copyright (C) 2013  Torsten Landschoff <torsten@debian.org> # # This file is part of paramiko. |
| **kex_group16.py** | $escapedPath | Utilities | # Copyright (C) 2019 Edgar Sousa <https://github.com/edgsousa> # # This file is part of paramiko. |
| **kex_gss.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # Copyright (C) 2013-2014 science + computing ag # Author: Sebastian Deiss <sebastian.deiss... |
| **message.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **packet.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **pipe.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **pkey.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **primes.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **proxy.py** | $escapedPath | Utilities | # Copyright (C) 2012  Yipit, Inc <coders@yipit.com> # # This file is part of paramiko. |
| **rsakey.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **server.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **sftp.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **sftp_attr.py** | $escapedPath | Utilities | # Copyright (C) 2003-2006 Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **sftp_client.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of Paramiko. |
| **sftp_file.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **sftp_handle.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **sftp_server.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **sftp_si.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **ssh_exception.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **ssh_gss.py** | $escapedPath | Utilities | # Copyright (C) 2013-2014 science + computing ag # Author: Sebastian Deiss <sebastian.deiss@t-online.de> # |
| **transport.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # |
| **util.py** | $escapedPath | Utilities | # Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com> # # This file is part of paramiko. |
| **win_openssh.py** | $escapedPath | Utilities | # Copyright (C) 2021 Lew Gordon <lew.gordon@genesys.com> # Copyright (C) 2022 Patrick Spendrin <ps_ml@gmx.de> # |
| **win_pageant.py** | $escapedPath | Utilities | # Copyright (C) 2005 John Arbash-Meinel <john@arbash-meinel.com> # Modified up by: Todd Whiteman <ToddW@ActiveState.com> # |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations __version__ = "25.3" def main(args: list[str] \| None = None) -> int: |
| **__main__.py** | $escapedPath | Utilities | import os import sys # Remove '' and current working directory from the first entry |
| **__pip-runner__.py** | $escapedPath | Utilities | """Execute exactly this copy of pip, within a different environment. This file is named as it is, to ensure that this module can't be imported via an import ... |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations from pip._internal.utils import _log # init_logging() must be called before any call to logging.getLogger() |
| **build_env.py** | $escapedPath | Utilities | """Build Environment used for isolation during sdist building""" from __future__ import annotations import logging |
| **cache.py** | $escapedPath | Utilities | """Cache Management""" from __future__ import annotations import hashlib |
| **__init__.py** | $escapedPath | Utilities | """Subpackage containing all of pip's command line interface related code""" # This file intentionally does not import submodules |
| **autocompletion.py** | $escapedPath | Utilities | """Logic that powers autocompletion installed by ``pip completion``.""" from __future__ import annotations import optparse |
| **base_command.py** | $escapedPath | Utilities | """Base Command class, and related routines""" from __future__ import annotations import logging |
| **cmdoptions.py** | $escapedPath | Utilities | """ shared options and groups The principle here is to define options once, but *not* instantiate them |
| **command_context.py** | $escapedPath | Utilities | from collections.abc import Generator from contextlib import AbstractContextManager, ExitStack, contextmanager from typing import TypeVar |
| **index_command.py** | $escapedPath | Utilities | """ Contains command classes which may interact with an index / the network. Unlike its sister module, req_command, this module still uses lazy imports |
| **main.py** | $escapedPath | Utilities | """Primary application entrypoint.""" from __future__ import annotations import locale |
| **main_parser.py** | $escapedPath | Utilities | """A single place for constructing and exposing the main parser""" from __future__ import annotations import os |
| **parser.py** | $escapedPath | Utilities | """Base option parser setup""" from __future__ import annotations import logging |
| **progress_bars.py** | $escapedPath | Utilities | from __future__ import annotations import functools import sys |
| **req_command.py** | $escapedPath | Utilities | """Contains the RequirementCommand base class. This class is in a separate module so the commands that do not always need PackageFinder capability don't unne... |
| **spinners.py** | $escapedPath | Utilities | from __future__ import annotations import contextlib import itertools |
| **status_codes.py** | $escapedPath | Utilities | SUCCESS = 0 ERROR = 1 UNKNOWN_ERROR = 2 |
| **__init__.py** | $escapedPath | Utilities | """ Package containing all pip commands """ |
| **cache.py** | $escapedPath | Utilities | import os import textwrap from optparse import Values |
| **check.py** | $escapedPath | Utilities | import logging from optparse import Values from pip._internal.cli.base_command import Command |
| **completion.py** | $escapedPath | Utilities | import sys import textwrap from optparse import Values |
| **configuration.py** | $escapedPath | Utilities | from __future__ import annotations import logging import os |
| **debug.py** | $escapedPath | Utilities | from __future__ import annotations import locale import logging |
| **download.py** | $escapedPath | Utilities | import logging import os from optparse import Values |
| **freeze.py** | $escapedPath | Utilities | import sys from optparse import Values from pip._internal.cli import cmdoptions |
| **hash.py** | $escapedPath | Utilities | import hashlib import logging import sys |
| **help.py** | $escapedPath | Utilities | from optparse import Values from pip._internal.cli.base_command import Command from pip._internal.cli.status_codes import SUCCESS |
| **index.py** | $escapedPath | Utilities | from __future__ import annotations import json import logging |
| **inspect.py** | $escapedPath | Utilities | import logging from optparse import Values from typing import Any |
| **install.py** | $escapedPath | Utilities | from __future__ import annotations import errno import json |
| **list.py** | $escapedPath | Utilities | from __future__ import annotations import json import logging |
| **lock.py** | $escapedPath | Utilities | import sys from optparse import Values from pathlib import Path |
| **search.py** | $escapedPath | Utilities | from __future__ import annotations import logging import shutil |
| **show.py** | $escapedPath | Utilities | from __future__ import annotations import logging import string |
| **uninstall.py** | $escapedPath | Utilities | import logging from optparse import Values from pip._vendor.packaging.utils import canonicalize_name |
| **wheel.py** | $escapedPath | Utilities | import logging import os import shutil |
| **configuration.py** | $escapedPath | Utilities | """Configuration management setup Some terminology: - name |
| **__init__.py** | $escapedPath | Utilities | from pip._internal.distributions.base import AbstractDistribution from pip._internal.distributions.sdist import SourceDistribution from pip._internal.distrib... |
| **base.py** | $escapedPath | Utilities | from __future__ import annotations import abc from typing import TYPE_CHECKING |
| **installed.py** | $escapedPath | Utilities | from __future__ import annotations from typing import TYPE_CHECKING from pip._internal.distributions.base import AbstractDistribution |
| **sdist.py** | $escapedPath | Utilities | from __future__ import annotations import logging from collections.abc import Iterable |
| **wheel.py** | $escapedPath | Utilities | from __future__ import annotations from typing import TYPE_CHECKING from pip._vendor.packaging.utils import canonicalize_name |
| **exceptions.py** | $escapedPath | Utilities | """Exceptions used throughout package. This module MUST NOT try to import from anything within `pip._internal` to operate. This is expected to be importable ... |
| **__init__.py** | $escapedPath | Utilities | """Index interaction code""" |
| **collector.py** | $escapedPath | Utilities | """ The main purpose of this module is to expose LinkCollector.collect_sources(). """ |
| **package_finder.py** | $escapedPath | Utilities | """Routines related to PyPI, indexes""" from __future__ import annotations import enum |
| **sources.py** | $escapedPath | Utilities | from __future__ import annotations import logging import mimetypes |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations import functools import logging |
| **_distutils.py** | $escapedPath | Utilities | """Locations where we look for configs, install stuff, etc""" # The following comment should be removed at some point in the future. # mypy: strict-optional=... |
| **_sysconfig.py** | $escapedPath | Utilities | from __future__ import annotations import logging import os |
| **base.py** | $escapedPath | Utilities | from __future__ import annotations import functools import os |
| **main.py** | $escapedPath | Utilities | from __future__ import annotations def main(args: list[str] \| None = None) -> int:     """This is preserved for old console scripts that may still be referen... |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations import contextlib import functools |
| **_json.py** | $escapedPath | Utilities | # Extracted from https://github.com/pfmoore/pkg_metadata from __future__ import annotations from email.header import Header, decode_header, make_header |
| **base.py** | $escapedPath | Utilities | from __future__ import annotations import csv import email.message |
| **__init__.py** | $escapedPath | Utilities | from ._dists import Distribution from ._envs import Environment __all__ = ["NAME", "Distribution", "Environment"] |
| **_compat.py** | $escapedPath | Utilities | from __future__ import annotations import importlib.metadata import os |
| **_dists.py** | $escapedPath | Utilities | from __future__ import annotations import email.message import importlib.metadata |
| **_envs.py** | $escapedPath | Utilities | from __future__ import annotations import importlib.metadata import logging |
| **pkg_resources.py** | $escapedPath | Utilities | from __future__ import annotations import email.message import email.parser |
| **__init__.py** | $escapedPath | Utilities | """A package that contains models that represent entities.""" |
| **candidate.py** | $escapedPath | Utilities | from dataclasses import dataclass from pip._vendor.packaging.version import Version from pip._vendor.packaging.version import parse as parse_version |
| **direct_url.py** | $escapedPath | Utilities | """PEP 610""" from __future__ import annotations import json |
| **format_control.py** | $escapedPath | Utilities | from __future__ import annotations from pip._vendor.packaging.utils import canonicalize_name from pip._internal.exceptions import CommandError |
| **index.py** | $escapedPath | Utilities | import urllib.parse class PackageIndex:     """Represents a Package Index and provides easier access to endpoints""" |
| **installation_report.py** | $escapedPath | Utilities | from collections.abc import Sequence from typing import Any from pip._vendor.packaging.markers import default_environment |
| **link.py** | $escapedPath | Utilities | from __future__ import annotations import functools import itertools |
| **pylock.py** | $escapedPath | Utilities | from __future__ import annotations import dataclasses import re |
| **scheme.py** | $escapedPath | Utilities | """ For types associated with installation schemes. For a general overview of available schemes and their context, see |
| **search_scope.py** | $escapedPath | Utilities | import itertools import logging import os |
| **selection_prefs.py** | $escapedPath | Utilities | from __future__ import annotations from pip._internal.models.format_control import FormatControl # TODO: This needs Python 3.10's improved slots support for ... |
| **target_python.py** | $escapedPath | Utilities | from __future__ import annotations import sys from pip._vendor.packaging.tags import Tag |
| **wheel.py** | $escapedPath | Utilities | """Represents a wheel file and provides access to the various parts of the name that have meaning. """ |
| **__init__.py** | $escapedPath | Utilities | """Contains purely network-related utilities.""" |
| **auth.py** | $escapedPath | Utilities | """Network Authentication Helpers Contains interface (MultiDomainBasicAuth) and associated glue code for providing credentials in the context of network requ... |
| **cache.py** | $escapedPath | Utilities | """HTTP cache implementation.""" from __future__ import annotations import os |
| **download.py** | $escapedPath | Utilities | """Download files with progress indicators.""" from __future__ import annotations import email.message |
| **lazy_wheel.py** | $escapedPath | Utilities | """Lazy ZIP over HTTP""" from __future__ import annotations __all__ = ["HTTPRangeRequestUnsupported", "dist_from_wheel_url"] |
| **session.py** | $escapedPath | Utilities | """PipSession and supporting code, containing all pip-specific network request configuration and behavior. """ |
| **utils.py** | $escapedPath | Utilities | from collections.abc import Generator from pip._vendor.requests.models import Response from pip._internal.exceptions import NetworkConnectionError |
| **xmlrpc.py** | $escapedPath | Utilities | """xmlrpclib.Transport implementation""" import logging import urllib.parse |
| **__init__.py** | $escapedPath | Utilities |  |
| **check.py** | $escapedPath | Utilities | """Validation of dependencies of packages""" from __future__ import annotations import logging |
| **freeze.py** | $escapedPath | Utilities | from __future__ import annotations import collections import logging |
| **__init__.py** | $escapedPath | Utilities | """For modules related to installing packages.""" |
| **wheel.py** | $escapedPath | Utilities | """Support for installing and building the "wheel" binary package format.""" from __future__ import annotations import collections |
| **prepare.py** | $escapedPath | Utilities | """Prepares a distribution for installation""" # The following comment should be removed at some point in the future. # mypy: strict-optional=False |
| **pyproject.py** | $escapedPath | Utilities | from __future__ import annotations import os from collections import namedtuple |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations import collections import logging |
| **constructors.py** | $escapedPath | Utilities | """Backing implementation for InstallRequirement's various constructors The idea here is that these formed a major chunk of InstallRequirement's size so, mov... |
| **req_dependency_group.py** | $escapedPath | Utilities | from collections.abc import Iterable, Iterator from typing import Any from pip._vendor.dependency_groups import DependencyGroupResolver |
| **req_file.py** | $escapedPath | Utilities | """ Requirements file parsing """ |
| **req_install.py** | $escapedPath | Utilities | from __future__ import annotations import functools import logging |
| **req_set.py** | $escapedPath | Utilities | import logging from collections import OrderedDict from pip._vendor.packaging.utils import canonicalize_name |
| **req_uninstall.py** | $escapedPath | Utilities | from __future__ import annotations import functools import os |
| **__init__.py** | $escapedPath | Utilities |  |
| **base.py** | $escapedPath | Utilities | from typing import Callable, Optional from pip._internal.req.req_install import InstallRequirement from pip._internal.req.req_set import RequirementSet |
| **__init__.py** | $escapedPath | Utilities |  |
| **resolver.py** | $escapedPath | Utilities | """Dependency Resolution The dependency resolution in pip is performed as follows: for top-level requirements: |
| **__init__.py** | $escapedPath | Utilities |  |
| **base.py** | $escapedPath | Utilities | from __future__ import annotations from collections.abc import Iterable from dataclasses import dataclass |
| **candidates.py** | $escapedPath | Utilities | from __future__ import annotations import logging import sys |
| **factory.py** | $escapedPath | Utilities | from __future__ import annotations import contextlib import functools |
| **found_candidates.py** | $escapedPath | Utilities | """Utilities to lazily create and visit candidates found. Creating and visiting a candidate is a *very* costly operation. It involves fetching, extracting, p... |
| **provider.py** | $escapedPath | Utilities | from __future__ import annotations import math from collections.abc import Iterable, Iterator, Mapping, Sequence |
| **reporter.py** | $escapedPath | Utilities | from __future__ import annotations from collections import defaultdict from collections.abc import Mapping |
| **requirements.py** | $escapedPath | Utilities | from __future__ import annotations from typing import Any from pip._vendor.packaging.specifiers import SpecifierSet |
| **resolver.py** | $escapedPath | Utilities | from __future__ import annotations import contextlib import functools |
| **self_outdated_check.py** | $escapedPath | Utilities | from __future__ import annotations import datetime import functools |
| **__init__.py** | $escapedPath | Utilities |  |
| **_jaraco_text.py** | $escapedPath | Utilities | """Functions brought over from jaraco.text. These functions are not supposed to be used within `pip._internal`. These are helper functions brought over from ... |
| **_log.py** | $escapedPath | Utilities | """Customize logging Defines custom logger class for the `logger.verbose(...)` method. init_logging() must be called before any other modules that call loggi... |
| **appdirs.py** | $escapedPath | Utilities | """ This code wraps the vendored appdirs module to so the return values are compatible for the current pip code base. |
| **compat.py** | $escapedPath | Utilities | """Stuff that differs in different Python versions and platform distributions.""" import importlib.resources |
| **compatibility_tags.py** | $escapedPath | Utilities | """Generate and work with PEP 425 Compatibility Tags.""" from __future__ import annotations import re |
| **datetime.py** | $escapedPath | Utilities | """For when pip wants to check the date or time.""" import datetime def today_is_later_than(year: int, month: int, day: int) -> bool: |
| **deprecation.py** | $escapedPath | Utilities | """ A module that implements tooling to enable easy warnings about deprecations. """ |
| **direct_url_helpers.py** | $escapedPath | Utilities | from __future__ import annotations from pip._internal.models.direct_url import ArchiveInfo, DirectUrl, DirInfo, VcsInfo from pip._internal.models.link import... |
| **egg_link.py** | $escapedPath | Utilities | from __future__ import annotations import os import re |
| **entrypoints.py** | $escapedPath | Utilities | from __future__ import annotations import itertools import os |
| **filesystem.py** | $escapedPath | Utilities | from __future__ import annotations import fnmatch import os |
| **filetypes.py** | $escapedPath | Utilities | """Filetype information.""" from pip._internal.utils.misc import splitext WHEEL_EXTENSION = ".whl" |
| **glibc.py** | $escapedPath | Utilities | from __future__ import annotations import os import sys |
| **hashes.py** | $escapedPath | Utilities | from __future__ import annotations import hashlib from collections.abc import Iterable |
| **logging.py** | $escapedPath | Utilities | from __future__ import annotations import contextlib import errno |
| **misc.py** | $escapedPath | Utilities | from __future__ import annotations import errno import getpass |
| **packaging.py** | $escapedPath | Utilities | from __future__ import annotations import functools import logging |
| **retry.py** | $escapedPath | Utilities | from __future__ import annotations import functools from time import perf_counter, sleep |
| **subprocess.py** | $escapedPath | Utilities | from __future__ import annotations import logging import os |
| **temp_dir.py** | $escapedPath | Utilities | from __future__ import annotations import errno import itertools |
| **unpacking.py** | $escapedPath | Utilities | """Utilities related archives.""" from __future__ import annotations import logging |
| **urls.py** | $escapedPath | Utilities | import os import string import urllib.parse |
| **virtualenv.py** | $escapedPath | Utilities | from __future__ import annotations import logging import os |
| **wheel.py** | $escapedPath | Utilities | """Support functions for working with wheel files.""" import logging from email.message import Message |
| **__init__.py** | $escapedPath | Utilities | # Expose a limited set of classes and functions so callers outside of # the vcs package don't need to import deeper than `pip._internal.vcs`. # (The test dir... |
| **bazaar.py** | $escapedPath | Utilities | from __future__ import annotations import logging from pip._internal.utils.misc import HiddenText, display_path |
| **git.py** | $escapedPath | Utilities | from __future__ import annotations import logging import os.path |
| **mercurial.py** | $escapedPath | Utilities | from __future__ import annotations import configparser import logging |
| **subversion.py** | $escapedPath | Utilities | from __future__ import annotations import logging import os |
| **versioncontrol.py** | $escapedPath | Utilities | """Handles all VCS (version control) support""" from __future__ import annotations import logging |
| **wheel_builder.py** | $escapedPath | Utilities | """Orchestrator for building wheels from InstallRequirements.""" from __future__ import annotations import logging |
| **__init__.py** | $escapedPath | Utilities | """ pip._vendor is for vendoring dependencies of pip to prevent needing pip to depend on something external. |
| **__init__.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **_cmd.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **adapter.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **cache.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **__init__.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **file_cache.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **redis_cache.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **controller.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **filewrapper.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **heuristics.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **serialize.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **wrapper.py** | $escapedPath | Utilities | # SPDX-FileCopyrightText: 2015 Eric Larson # # SPDX-License-Identifier: Apache-2.0 |
| **__init__.py** | $escapedPath | Utilities | from .core import contents, where __all__ = ["contents", "where"] __version__ = "2025.10.05" |
| **__main__.py** | $escapedPath | Utilities | import argparse from pip._vendor.certifi import contents, where parser = argparse.ArgumentParser() |
| **core.py** | $escapedPath | Utilities | """ certifi.py ~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | from ._implementation import (     CyclicDependencyError,     DependencyGroupInclude, |
| **__main__.py** | $escapedPath | Utilities | import argparse import sys from ._implementation import resolve |
| **_implementation.py** | $escapedPath | Utilities | from __future__ import annotations import dataclasses import re |
| **_lint_dependency_groups.py** | $escapedPath | Utilities | from __future__ import annotations import argparse import sys |
| **_pip_wrapper.py** | $escapedPath | Utilities | from __future__ import annotations import argparse import subprocess |
| **_toml_compat.py** | $escapedPath | Utilities | try:     import tomllib except ImportError: |
| **__init__.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- # # Copyright (C) 2012-2024 Vinay Sajip. |
| **compat.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- # # Copyright (C) 2013-2017 Vinay Sajip. |
| **resources.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- # # Copyright (C) 2013-2017 Vinay Sajip. |
| **scripts.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- # # Copyright (C) 2013-2023 Vinay Sajip. |
| **util.py** | $escapedPath | Utilities | # # Copyright (C) 2012-2023 The Python Software Foundation. # See LICENSE.txt and CONTRIBUTORS.txt. |
| **__init__.py** | $escapedPath | Utilities | from .distro import (     NORMALIZED_DISTRO_ID,     NORMALIZED_LSB_ID, |
| **__main__.py** | $escapedPath | Utilities | from .distro import main if __name__ == "__main__":     main() |
| **distro.py** | $escapedPath | Utilities | #!/usr/bin/env python # Copyright 2015-2021 Nir Cohen # |
| **__init__.py** | $escapedPath | Utilities | from .core import (     IDNABidiError,     IDNAError, |
| **codec.py** | $escapedPath | Utilities | import codecs import re from typing import Any, Optional, Tuple |
| **compat.py** | $escapedPath | Utilities | from typing import Any, Union from .core import decode, encode def ToASCII(label: str) -> bytes: |
| **core.py** | $escapedPath | Utilities | import bisect import re import unicodedata |
| **idnadata.py** | $escapedPath | Utilities | # This file is automatically generated by tools/idna-data __version__ = "15.1.0" scripts = { |
| **intranges.py** | $escapedPath | Utilities | """ Given a list of integers, made up of (hopefully) a small number of long runs of consecutive integers, compute a representation of the form |
| **package_data.py** | $escapedPath | Utilities | __version__ = "3.10" |
| **uts46data.py** | $escapedPath | Utilities | # This file is automatically generated by tools/idna-data # vim: set fileencoding=utf-8 : from typing import List, Tuple, Union |
| **__init__.py** | $escapedPath | Utilities | # ruff: noqa: F401 import os from .exceptions import *  # noqa: F403 |
| **exceptions.py** | $escapedPath | Utilities | class UnpackException(Exception):     """Base class for some exceptions raised while unpacking.     NOTE: unpack may raise exception other than subclass of |
| **ext.py** | $escapedPath | Utilities | import datetime import struct from collections import namedtuple |
| **fallback.py** | $escapedPath | Utilities | """Fallback pure Python implementation of msgpack""" import struct import sys |
| **__init__.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_elffile.py** | $escapedPath | Utilities | """ ELF file parser. This provides a class ``ELFFile`` that parses an ELF executable in a similar |
| **_manylinux.py** | $escapedPath | Utilities | from __future__ import annotations import collections import contextlib |
| **_musllinux.py** | $escapedPath | Utilities | """PEP 656 support. This module implements logic to detect if the currently running Python is linked against musl, and what musl version is used. |
| **_parser.py** | $escapedPath | Utilities | """Handwritten parser of dependency specifiers. The docstring for each __parse_* function contains EBNF-inspired grammar representing the implementation. |
| **_structures.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **_tokenizer.py** | $escapedPath | Utilities | from __future__ import annotations import contextlib import re |
| **__init__.py** | $escapedPath | Utilities | ####################################################################################### # # Adapted from: |
| **_spdx.py** | $escapedPath | Utilities | from __future__ import annotations from typing import TypedDict class SPDXLicense(TypedDict): |
| **markers.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **metadata.py** | $escapedPath | Utilities | from __future__ import annotations import email.feedparser import email.header |
| **requirements.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **specifiers.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **tags.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **utils.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **version.py** | $escapedPath | Utilities | # This file is dual licensed under the terms of the Apache License, Version # 2.0, and the BSD License. See the LICENSE file in the root of this repository #... |
| **__init__.py** | $escapedPath | Utilities | # TODO: Add Generic type annotations to initialized collections. # For now we'd simply use implicit Any/Unknown which would add redundant annotations # mypy:... |
| **__init__.py** | $escapedPath | Utilities | """ Utilities for determining application-specific dirs. See <https://github.com/platformdirs/platformdirs> for details and usage. |
| **__main__.py** | $escapedPath | Utilities | """Main entry point.""" from __future__ import annotations from pip._vendor.platformdirs import PlatformDirs, __version__ |
| **android.py** | $escapedPath | Utilities | """Android.""" from __future__ import annotations import os |
| **api.py** | $escapedPath | Utilities | """Base API.""" from __future__ import annotations import os |
| **macos.py** | $escapedPath | Utilities | """macOS.""" from __future__ import annotations import os.path |
| **unix.py** | $escapedPath | Utilities | """Unix.""" from __future__ import annotations import os |
| **version.py** | $escapedPath | Utilities | # file generated by setuptools-scm # don't change, don't track in version control __all__ = [ |
| **windows.py** | $escapedPath | Utilities | """Windows.""" from __future__ import annotations import os |
| **__init__.py** | $escapedPath | Utilities | """     Pygments     ~~~~~~~~ |
| **__main__.py** | $escapedPath | Utilities | """     pygments.__main__     ~~~~~~~~~~~~~~~~~ |
| **console.py** | $escapedPath | Utilities | """     pygments.console     ~~~~~~~~~~~~~~~~ |
| **filter.py** | $escapedPath | Utilities | """     pygments.filter     ~~~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | """     pygments.filters     ~~~~~~~~~~~~~~~~ |
| **formatter.py** | $escapedPath | Utilities | """     pygments.formatter     ~~~~~~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | """     pygments.formatters     ~~~~~~~~~~~~~~~~~~~ |
| **_mapping.py** | $escapedPath | Utilities | # Automatically generated by scripts/gen_mapfiles.py. # DO NOT EDIT BY HAND; run `tox -e mapfiles` instead. FORMATTERS = { |
| **lexer.py** | $escapedPath | Utilities | """     pygments.lexer     ~~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | """     pygments.lexers     ~~~~~~~~~~~~~~~ |
| **_mapping.py** | $escapedPath | Utilities | # Automatically generated by scripts/gen_mapfiles.py. # DO NOT EDIT BY HAND; run `tox -e mapfiles` instead. LEXERS = { |
| **python.py** | $escapedPath | Utilities | """     pygments.lexers.python     ~~~~~~~~~~~~~~~~~~~~~~ |
| **modeline.py** | $escapedPath | Utilities | """     pygments.modeline     ~~~~~~~~~~~~~~~~~ |
| **plugin.py** | $escapedPath | Utilities | """     pygments.plugin     ~~~~~~~~~~~~~~~ |
| **regexopt.py** | $escapedPath | Utilities | """     pygments.regexopt     ~~~~~~~~~~~~~~~~~ |
| **scanner.py** | $escapedPath | Utilities | """     pygments.scanner     ~~~~~~~~~~~~~~~~ |
| **sphinxext.py** | $escapedPath | Utilities | """     pygments.sphinxext     ~~~~~~~~~~~~~~~~~~ |
| **style.py** | $escapedPath | Utilities | """     pygments.style     ~~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | """     pygments.styles     ~~~~~~~~~~~~~~~ |
| **_mapping.py** | $escapedPath | Utilities | # Automatically generated by scripts/gen_mapfiles.py. # DO NOT EDIT BY HAND; run `tox -e mapfiles` instead. STYLES = { |
| **token.py** | $escapedPath | Utilities | """     pygments.token     ~~~~~~~~~~~~~~ |
| **unistring.py** | $escapedPath | Utilities | """     pygments.unistring     ~~~~~~~~~~~~~~~~~~ |
| **util.py** | $escapedPath | Utilities | """     pygments.util     ~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | """Wrappers to call pyproject.toml-based build backend hooks. """ from typing import TYPE_CHECKING |
| **_impl.py** | $escapedPath | Utilities | import json import os import sys |
| **__init__.py** | $escapedPath | Utilities | """This is a subpackage because the directory is on sys.path for _in_process.py The subpackage should stay as empty as possible to avoid shadowing modules th... |
| **_in_process.py** | $escapedPath | Utilities | """This is invoked in a subprocess to call the build backend hooks. It expects: - Command line args: hook_name, control_dir |
| **__init__.py** | $escapedPath | Utilities | #   __ #  /__)  _  _     _   _ _/   _ # / (   (- (/ (/ (- _)  /  _) |
| **__version__.py** | $escapedPath | Utilities | # .-. .-. .-. . . .-. .-. .-. .-. # \|(  \|-  \|.\| \| \| \|-  `-.  \|  `-. # ' ' `-' `-`.`-' `-' `-'  '  `-' |
| **_internal_utils.py** | $escapedPath | Utilities | """ requests._internal_utils ~~~~~~~~~~~~~~ |
| **adapters.py** | $escapedPath | Utilities | """ requests.adapters ~~~~~~~~~~~~~~~~~ |
| **api.py** | $escapedPath | Utilities | """ requests.api ~~~~~~~~~~~~ |
| **auth.py** | $escapedPath | Utilities | """ requests.auth ~~~~~~~~~~~~~ |
| **certs.py** | $escapedPath | Utilities | #!/usr/bin/env python """ requests.certs |
| **compat.py** | $escapedPath | Utilities | """ requests.compat ~~~~~~~~~~~~~~~ |
| **cookies.py** | $escapedPath | Utilities | """ requests.cookies ~~~~~~~~~~~~~~~~ |
| **exceptions.py** | $escapedPath | Utilities | """ requests.exceptions ~~~~~~~~~~~~~~~~~~~ |
| **help.py** | $escapedPath | Utilities | """Module containing bug report helper(s).""" import json import platform |
| **hooks.py** | $escapedPath | Utilities | """ requests.hooks ~~~~~~~~~~~~~~ |
| **models.py** | $escapedPath | Utilities | """ requests.models ~~~~~~~~~~~~~~~ |
| **packages.py** | $escapedPath | Utilities | import sys from .compat import chardet # This code exists for backwards compatibility reasons. |
| **sessions.py** | $escapedPath | Utilities | """ requests.sessions ~~~~~~~~~~~~~~~~~ |
| **status_codes.py** | $escapedPath | Utilities | r""" The ``codes`` object defines a mapping from common names for HTTP statuses to their numerical codes, accessible either as attributes or as dictionary |
| **structures.py** | $escapedPath | Utilities | """ requests.structures ~~~~~~~~~~~~~~~~~~~ |
| **utils.py** | $escapedPath | Utilities | """ requests.utils ~~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | __all__ = [     "AbstractProvider",     "AbstractResolver", |
| **providers.py** | $escapedPath | Utilities | from __future__ import annotations from typing import (     TYPE_CHECKING, |
| **reporters.py** | $escapedPath | Utilities | from __future__ import annotations from typing import TYPE_CHECKING, Collection, Generic from .structs import CT, KT, RT, RequirementInformation, State |
| **__init__.py** | $escapedPath | Utilities | from ..structs import RequirementInformation from .abstract import AbstractResolver, Result from .criterion import Criterion |
| **abstract.py** | $escapedPath | Utilities | from __future__ import annotations import collections from typing import TYPE_CHECKING, Any, Generic, Iterable, NamedTuple |
| **criterion.py** | $escapedPath | Utilities | from __future__ import annotations from typing import Collection, Generic, Iterable, Iterator from ..structs import CT, RT, RequirementInformation |
| **exceptions.py** | $escapedPath | Utilities | from __future__ import annotations from typing import TYPE_CHECKING, Collection, Generic from ..structs import CT, RT, RequirementInformation |
| **resolution.py** | $escapedPath | Utilities | from __future__ import annotations import collections import itertools |
| **structs.py** | $escapedPath | Utilities | from __future__ import annotations import itertools from collections import namedtuple |
| **__init__.py** | $escapedPath | Utilities | """Rich text and beautiful formatting in the terminal.""" import os from typing import IO, TYPE_CHECKING, Any, Callable, Optional, Union |
| **__main__.py** | $escapedPath | Utilities | import colorsys import io from time import process_time |
| **_cell_widths.py** | $escapedPath | Utilities | # Auto generated by make_terminal_widths.py CELL_WIDTHS = [     (0, 0, 0), |
| **_emoji_codes.py** | $escapedPath | Utilities | EMOJI = {     "1st_place_medal": "рџҐ‡",     "2nd_place_medal": "рџҐ€", |
| **_emoji_replace.py** | $escapedPath | Utilities | from typing import Callable, Match, Optional import re from ._emoji_codes import EMOJI |
| **_export_format.py** | $escapedPath | Utilities | CONSOLE_HTML_FORMAT = """\ <!DOCTYPE html> <html> |
| **_extension.py** | $escapedPath | Utilities | from typing import Any def load_ipython_extension(ip: Any) -> None:  # pragma: no cover     # prevent circular import |
| **_fileno.py** | $escapedPath | Utilities | from __future__ import annotations from typing import IO, Callable def get_fileno(file_like: IO[str]) -> int \| None: |
| **_inspect.py** | $escapedPath | Utilities | import inspect from inspect import cleandoc, getdoc, getfile, isclass, ismodule, signature from typing import Any, Collection, Iterable, Optional, Tuple, Typ... |
| **_log_render.py** | $escapedPath | Utilities | from datetime import datetime from typing import Iterable, List, Optional, TYPE_CHECKING, Union, Callable from .text import Text, TextType |
| **_loop.py** | $escapedPath | Utilities | from typing import Iterable, Tuple, TypeVar T = TypeVar("T") def loop_first(values: Iterable[T]) -> Iterable[Tuple[bool, T]]: |
| **_null_file.py** | $escapedPath | Utilities | from types import TracebackType from typing import IO, Iterable, Iterator, List, Optional, Type class NullFile(IO[str]): |
| **_palettes.py** | $escapedPath | Utilities | from .palette import Palette # Taken from https://en.wikipedia.org/wiki/ANSI_escape_code (Windows 10 column) WINDOWS_PALETTE = Palette( |
| **_pick.py** | $escapedPath | Utilities | from typing import Optional def pick_bool(*values: Optional[bool]) -> bool:     """Pick the first non-none bool or return the last value. |
| **_ratio.py** | $escapedPath | Utilities | from fractions import Fraction from math import ceil from typing import cast, List, Optional, Sequence, Protocol |
| **_spinners.py** | $escapedPath | Utilities | """ Spinners are from: * cli-spinners: |
| **_stack.py** | $escapedPath | Utilities | from typing import List, TypeVar T = TypeVar("T") class Stack(List[T]): |
| **_timer.py** | $escapedPath | Utilities | """ Timer context manager, only used in debug. """ |
| **_win32_console.py** | $escapedPath | Utilities | """Light wrapper around the Win32 Console API - this module should only be imported on Windows The API that this module wraps is documented at https://docs.m... |
| **_windows.py** | $escapedPath | Utilities | import sys from dataclasses import dataclass @dataclass |
| **_windows_renderer.py** | $escapedPath | Utilities | from typing import Iterable, Sequence, Tuple, cast from pip._vendor.rich._win32_console import LegacyWindowsTerm, WindowsCoordinates from pip._vendor.rich.se... |
| **_wrap.py** | $escapedPath | Utilities | from __future__ import annotations import re from typing import Iterable |
| **abc.py** | $escapedPath | Utilities | from abc import ABC class RichRenderable(ABC):     """An abstract base class for Rich renderables. |
| **align.py** | $escapedPath | Utilities | from itertools import chain from typing import TYPE_CHECKING, Iterable, Optional, Literal from .constrain import Constrain |
| **ansi.py** | $escapedPath | Utilities | import re import sys from contextlib import suppress |
| **bar.py** | $escapedPath | Utilities | from typing import Optional, Union from .color import Color from .console import Console, ConsoleOptions, RenderResult |
| **box.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING, Iterable, List, Literal from ._loop import loop_last if TYPE_CHECKING: |
| **cells.py** | $escapedPath | Utilities | from __future__ import annotations from functools import lru_cache from typing import Callable |
| **color.py** | $escapedPath | Utilities | import re import sys from colorsys import rgb_to_hls |
| **color_triplet.py** | $escapedPath | Utilities | from typing import NamedTuple, Tuple class ColorTriplet(NamedTuple):     """The red, green, and blue components of a color.""" |
| **columns.py** | $escapedPath | Utilities | from collections import defaultdict from itertools import chain from operator import itemgetter |
| **console.py** | $escapedPath | Utilities | import inspect import os import sys |
| **constrain.py** | $escapedPath | Utilities | from typing import Optional, TYPE_CHECKING from .jupyter import JupyterMixin from .measure import Measurement |
| **containers.py** | $escapedPath | Utilities | from itertools import zip_longest from typing import (     TYPE_CHECKING, |
| **control.py** | $escapedPath | Utilities | import time from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Union, Final from .segment import ControlCode, ControlType, Segment |
| **default_styles.py** | $escapedPath | Utilities | from typing import Dict from .style import Style DEFAULT_STYLES: Dict[str, Style] = { |
| **diagnose.py** | $escapedPath | Utilities | import os import platform from pip._vendor.rich import inspect |
| **emoji.py** | $escapedPath | Utilities | import sys from typing import TYPE_CHECKING, Optional, Union, Literal from .jupyter import JupyterMixin |
| **errors.py** | $escapedPath | Utilities | class ConsoleError(Exception):     """An error in console operation.""" class StyleError(Exception): |
| **file_proxy.py** | $escapedPath | Utilities | import io from typing import IO, TYPE_CHECKING, Any, List from .ansi import AnsiDecoder |
| **filesize.py** | $escapedPath | Utilities | """Functions for reporting filesizes. Borrowed from https://github.com/PyFilesystem/pyfilesystem2 The functions declared in this module should cover the diff... |
| **highlighter.py** | $escapedPath | Utilities | import re from abc import ABC, abstractmethod from typing import List, Union |
| **json.py** | $escapedPath | Utilities | from pathlib import Path from json import loads, dumps from typing import Any, Callable, Optional, Union |
| **jupyter.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Sequence if TYPE_CHECKING:     from pip._vendor.rich.console import ConsoleRenderable |
| **layout.py** | $escapedPath | Utilities | from abc import ABC, abstractmethod from itertools import islice from operator import itemgetter |
| **live.py** | $escapedPath | Utilities | from __future__ import annotations import sys from threading import Event, RLock, Thread |
| **live_render.py** | $escapedPath | Utilities | from typing import Optional, Tuple, Literal from ._loop import loop_last from .console import Console, ConsoleOptions, RenderableType, RenderResult |
| **logging.py** | $escapedPath | Utilities | import logging from datetime import datetime from logging import Handler, LogRecord |
| **markup.py** | $escapedPath | Utilities | import re from ast import literal_eval from operator import attrgetter |
| **measure.py** | $escapedPath | Utilities | from operator import itemgetter from typing import TYPE_CHECKING, Callable, NamedTuple, Optional, Sequence from . import errors |
| **padding.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING, List, Optional, Tuple, Union if TYPE_CHECKING:     from .console import ( |
| **pager.py** | $escapedPath | Utilities | from abc import ABC, abstractmethod from typing import Any class Pager(ABC): |
| **palette.py** | $escapedPath | Utilities | from math import sqrt from functools import lru_cache from typing import Sequence, Tuple, TYPE_CHECKING |
| **panel.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING, Optional from .align import AlignMethod from .box import ROUNDED, Box |
| **pretty.py** | $escapedPath | Utilities | import builtins import collections import dataclasses |
| **progress.py** | $escapedPath | Utilities | from __future__ import annotations import io import typing |
| **progress_bar.py** | $escapedPath | Utilities | import math from functools import lru_cache from time import monotonic |
| **prompt.py** | $escapedPath | Utilities | from typing import Any, Generic, List, Optional, TextIO, TypeVar, Union, overload from . import get_console from .console import Console |
| **protocol.py** | $escapedPath | Utilities | from typing import Any, cast, Set, TYPE_CHECKING from inspect import isclass if TYPE_CHECKING: |
| **region.py** | $escapedPath | Utilities | from typing import NamedTuple class Region(NamedTuple):     """Defines a rectangular region of the screen.""" |
| **repr.py** | $escapedPath | Utilities | import inspect from functools import partial from typing import ( |
| **rule.py** | $escapedPath | Utilities | from typing import Union from .align import AlignMethod from .cells import cell_len, set_cell_size |
| **scope.py** | $escapedPath | Utilities | from collections.abc import Mapping from typing import TYPE_CHECKING, Any, Optional, Tuple from .highlighter import ReprHighlighter |
| **screen.py** | $escapedPath | Utilities | from typing import Optional, TYPE_CHECKING from .segment import Segment from .style import StyleType |
| **segment.py** | $escapedPath | Utilities | from enum import IntEnum from functools import lru_cache from itertools import filterfalse |
| **spinner.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING, List, Optional, Union, cast from ._spinners import SPINNERS from .measure import Measurement |
| **status.py** | $escapedPath | Utilities | from types import TracebackType from typing import Optional, Type from .console import Console, RenderableType |
| **style.py** | $escapedPath | Utilities | import sys from functools import lru_cache from operator import attrgetter |
| **styled.py** | $escapedPath | Utilities | from typing import TYPE_CHECKING from .measure import Measurement from .segment import Segment |
| **syntax.py** | $escapedPath | Utilities | from __future__ import annotations import os.path import re |
| **table.py** | $escapedPath | Utilities | from dataclasses import dataclass, field, replace from typing import (     TYPE_CHECKING, |
| **terminal_theme.py** | $escapedPath | Utilities | from typing import List, Optional, Tuple from .color_triplet import ColorTriplet from .palette import Palette |
| **text.py** | $escapedPath | Utilities | import re from functools import partial, reduce from math import gcd |
| **theme.py** | $escapedPath | Utilities | import configparser from typing import IO, Dict, List, Mapping, Optional from .default_styles import DEFAULT_STYLES |
| **themes.py** | $escapedPath | Utilities | from .default_styles import DEFAULT_STYLES from .theme import Theme DEFAULT = Theme(DEFAULT_STYLES) |
| **traceback.py** | $escapedPath | Utilities | import inspect import linecache import os |
| **tree.py** | $escapedPath | Utilities | from typing import Iterator, List, Optional, Tuple from ._loop import loop_first, loop_last from .console import Console, ConsoleOptions, RenderableType, Ren... |
| **__init__.py** | $escapedPath | Utilities | # SPDX-License-Identifier: MIT # SPDX-FileCopyrightText: 2021 Taneli Hukkinen # Licensed to PSF under a Contributor Agreement. |
| **_parser.py** | $escapedPath | Utilities | # SPDX-License-Identifier: MIT # SPDX-FileCopyrightText: 2021 Taneli Hukkinen # Licensed to PSF under a Contributor Agreement. |
| **_re.py** | $escapedPath | Utilities | # SPDX-License-Identifier: MIT # SPDX-FileCopyrightText: 2021 Taneli Hukkinen # Licensed to PSF under a Contributor Agreement. |
| **_types.py** | $escapedPath | Utilities | # SPDX-License-Identifier: MIT # SPDX-FileCopyrightText: 2021 Taneli Hukkinen # Licensed to PSF under a Contributor Agreement. |
| **__init__.py** | $escapedPath | Utilities | __all__ = ("dumps", "dump") __version__ = "1.2.0"  # DO NOT EDIT THIS LINE MANUALLY. LET bump2version UTILITY DO IT from pip._vendor.tomli_w._writer import d... |
| **_writer.py** | $escapedPath | Utilities | from __future__ import annotations from collections.abc import Mapping from datetime import date, datetime, time |
| **__init__.py** | $escapedPath | Utilities | """Verify certificates using native system trust stores""" import sys as _sys if _sys.version_info < (3, 10): |
| **_api.py** | $escapedPath | Utilities | import contextlib import os import platform |
| **_macos.py** | $escapedPath | Utilities | import contextlib import ctypes import platform |
| **_openssl.py** | $escapedPath | Utilities | import contextlib import os import re |
| **_ssl_constants.py** | $escapedPath | Utilities | import ssl import sys import typing |
| **_windows.py** | $escapedPath | Utilities | import contextlib import ssl import typing |
| **__init__.py** | $escapedPath | Utilities | """ Python HTTP library with thread-safe connection pooling, file post support, user friendly, and more """ |
| **_collections.py** | $escapedPath | Utilities | from __future__ import absolute_import try:     from collections.abc import Mapping, MutableMapping |
| **_version.py** | $escapedPath | Utilities | # This file is protected via CODEOWNERS __version__ = "1.26.20" |
| **connection.py** | $escapedPath | Utilities | from __future__ import absolute_import import datetime import logging |
| **connectionpool.py** | $escapedPath | Utilities | from __future__ import absolute_import import errno import logging |
| **__init__.py** | $escapedPath | Utilities |  |
| **_appengine_environ.py** | $escapedPath | Utilities | """ This module provides means to detect the App Engine environment. """ |
| **__init__.py** | $escapedPath | Utilities |  |
| **bindings.py** | $escapedPath | Utilities | """ This module uses ctypes to bind a whole bunch of functions and constants from SecureTransport. The goal here is to provide the low-level API to |
| **low_level.py** | $escapedPath | Utilities | """ Low-level helpers for the SecureTransport bindings. These are Python functions that are not directly related to the high-level APIs |
| **appengine.py** | $escapedPath | Utilities | """ This module provides a pool manager that uses Google App Engine's `URLFetch Service <https://cloud.google.com/appengine/docs/python/urlfetch>`_. |
| **ntlmpool.py** | $escapedPath | Utilities | """ NTLM authenticating pool, contributed by erikcederstran Issue #10, see: http://code.google.com/p/urllib3/issues/detail?id=10 |
| **pyopenssl.py** | $escapedPath | Utilities | """ TLS with SNI_-support for Python 2. Follow these instructions if you would like to verify TLS certificates in Python 2. Note, the default libraries do |
| **securetransport.py** | $escapedPath | Utilities | """ SecureTranport support for urllib3 via ctypes. This makes platform-native TLS available to urllib3 users on macOS without the |
| **socks.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- """ This module contains provisional support for SOCKS proxies from within |
| **exceptions.py** | $escapedPath | Utilities | from __future__ import absolute_import from .packages.six.moves.http_client import IncompleteRead as httplib_IncompleteRead # Base Exceptions |
| **fields.py** | $escapedPath | Utilities | from __future__ import absolute_import import email.utils import mimetypes |
| **filepost.py** | $escapedPath | Utilities | from __future__ import absolute_import import binascii import codecs |
| **__init__.py** | $escapedPath | Utilities |  |
| **__init__.py** | $escapedPath | Utilities |  |
| **makefile.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- """ backports.makefile |
| **weakref_finalize.py** | $escapedPath | Utilities | # -*- coding: utf-8 -*- """ backports.weakref_finalize |
| **six.py** | $escapedPath | Utilities | # Copyright (c) 2010-2020 Benjamin Peterson # # Permission is hereby granted, free of charge, to any person obtaining a copy |
| **poolmanager.py** | $escapedPath | Utilities | from __future__ import absolute_import import collections import functools |
| **request.py** | $escapedPath | Utilities | from __future__ import absolute_import import sys from .filepost import encode_multipart_formdata |
| **response.py** | $escapedPath | Utilities | from __future__ import absolute_import import io import logging |
| **__init__.py** | $escapedPath | Utilities | from __future__ import absolute_import # For backwards compatibility, provide imports that used to be here. from .connection import is_connection_dropped |
| **connection.py** | $escapedPath | Utilities | from __future__ import absolute_import import socket from ..contrib import _appengine_environ |
| **proxy.py** | $escapedPath | Utilities | from .ssl_ import create_urllib3_context, resolve_cert_reqs, resolve_ssl_version def connection_requires_http_tunnel(     proxy_url=None, proxy_config=None, ... |
| **queue.py** | $escapedPath | Utilities | import collections from ..packages import six from ..packages.six.moves import queue |
| **request.py** | $escapedPath | Utilities | from __future__ import absolute_import from base64 import b64encode from ..exceptions import UnrewindableBodyError |
| **response.py** | $escapedPath | Utilities | from __future__ import absolute_import from email.errors import MultipartInvariantViolationDefect, StartBoundaryNotFoundDefect from ..exceptions import Heade... |
| **retry.py** | $escapedPath | Utilities | from __future__ import absolute_import import email import logging |
| **ssl_.py** | $escapedPath | Utilities | from __future__ import absolute_import import hashlib import hmac |
| **ssl_match_hostname.py** | $escapedPath | Utilities | """The match_hostname() function from Python 3.3.3, essential when using SSL.""" # Note: This file is under the PSF license as the code comes from the python... |
| **ssltransport.py** | $escapedPath | Utilities | import io import socket import ssl |
| **timeout.py** | $escapedPath | Utilities | from __future__ import absolute_import import time # The default socket timeout, used by httplib to indicate that no timeout was; specified by the user |
| **url.py** | $escapedPath | Utilities | from __future__ import absolute_import import re from collections import namedtuple |
| **wait.py** | $escapedPath | Utilities | import errno import select import sys |
| **__init__.py** | $escapedPath | Utilities | #----------------------------------------------------------------- # pycparser: __init__.py # |
| **_ast_gen.py** | $escapedPath | Utilities | #----------------------------------------------------------------- # _ast_gen.py # |
| **_build_tables.py** | $escapedPath | Utilities | #----------------------------------------------------------------- # pycparser: _build_tables.py # |
| **ast_transforms.py** | $escapedPath | Utilities | #------------------------------------------------------------------------------ # pycparser: ast_transforms.py # |
| **c_ast.py** | $escapedPath | Utilities | #----------------------------------------------------------------- # ** ATTENTION ** # This code was automatically generated from the file: |
| **c_generator.py** | $escapedPath | Utilities | #------------------------------------------------------------------------------ # pycparser: c_generator.py # |
| **c_lexer.py** | $escapedPath | Utilities | #------------------------------------------------------------------------------ # pycparser: c_lexer.py # |
| **c_parser.py** | $escapedPath | Utilities | #------------------------------------------------------------------------------ # pycparser: c_parser.py # |
| **lextab.py** | $escapedPath | Utilities | # lextab.py. This file automatically created by PLY (version 3.10). Don't edit! _tabversion   = '3.10' _lextokens    = set(('AND', 'ANDEQUAL', 'ARROW', 'AUTO... |
| **__init__.py** | $escapedPath | Utilities | # PLY package # Author: David Beazley (dave@dabeaz.com) __version__ = '3.9' |
| **cpp.py** | $escapedPath | Utilities | # ----------------------------------------------------------------------------- # cpp.py # |
| **ctokens.py** | $escapedPath | Utilities | # ---------------------------------------------------------------------- # ctokens.py # |
| **lex.py** | $escapedPath | Utilities | # ----------------------------------------------------------------------------- # ply: lex.py # |
| **yacc.py** | $escapedPath | Utilities | # ----------------------------------------------------------------------------- # ply: yacc.py # |
| **ygen.py** | $escapedPath | Utilities | # ply: ygen.py # # This is a support program that auto-generates different versions of the YACC parsing |
| **plyparser.py** | $escapedPath | Utilities | #----------------------------------------------------------------- # plyparser.py # |
| **yacctab.py** | $escapedPath | Utilities | # yacctab.py # This file is automatically generated. Do not edit. _tabversion = '3.10' |
| **__init__.py** | $escapedPath | Utilities | #   __ #  /__)  _  _     _   _ _/   _ # / (   (- (/ (/ (- _)  /  _) |
| **__version__.py** | $escapedPath | Utilities | # .-. .-. .-. . . .-. .-. .-. .-. # \|(  \|-  \|.\| \| \| \|-  `-.  \|  `-. # ' ' `-' `-`.`-' `-' `-'  '  `-' |
| **_internal_utils.py** | $escapedPath | Utilities | """ requests._internal_utils ~~~~~~~~~~~~~~ |
| **adapters.py** | $escapedPath | Utilities | """ requests.adapters ~~~~~~~~~~~~~~~~~ |
| **api.py** | $escapedPath | Utilities | """ requests.api ~~~~~~~~~~~~ |
| **auth.py** | $escapedPath | Utilities | """ requests.auth ~~~~~~~~~~~~~ |
| **certs.py** | $escapedPath | Utilities | #!/usr/bin/env python """ requests.certs |
| **compat.py** | $escapedPath | Utilities | """ requests.compat ~~~~~~~~~~~~~~~ |
| **cookies.py** | $escapedPath | Utilities | """ requests.cookies ~~~~~~~~~~~~~~~~ |
| **exceptions.py** | $escapedPath | Utilities | """ requests.exceptions ~~~~~~~~~~~~~~~~~~~ |
| **help.py** | $escapedPath | Utilities | """Module containing bug report helper(s).""" import json import platform |
| **hooks.py** | $escapedPath | Utilities | """ requests.hooks ~~~~~~~~~~~~~~ |
| **models.py** | $escapedPath | Utilities | """ requests.models ~~~~~~~~~~~~~~~ |
| **packages.py** | $escapedPath | Utilities | import sys from .compat import chardet # This code exists for backwards compatibility reasons. |
| **sessions.py** | $escapedPath | Utilities | """ requests.sessions ~~~~~~~~~~~~~~~~~ |
| **status_codes.py** | $escapedPath | Utilities | r""" The ``codes`` object defines a mapping from common names for HTTP statuses to their numerical codes, accessible either as attributes or as dictionary |
| **structures.py** | $escapedPath | Utilities | """ requests.structures ~~~~~~~~~~~~~~~~~~~ |
| **utils.py** | $escapedPath | Utilities | """ requests.utils ~~~~~~~~~~~~~~ |
| **__init__.py** | $escapedPath | Utilities | """ Python HTTP library with thread-safe connection pooling, file post support, user friendly, and more """ |
| **_base_connection.py** | $escapedPath | Utilities | from __future__ import annotations import typing from .util.connection import _TYPE_SOCKET_OPTIONS |
| **_collections.py** | $escapedPath | Utilities | from __future__ import annotations import typing from collections import OrderedDict |
| **_request_methods.py** | $escapedPath | Utilities | from __future__ import annotations import json as _json import typing |
| **_version.py** | $escapedPath | Utilities | # file generated by setuptools-scm # don't change, don't track in version control __all__ = [ |
| **connection.py** | $escapedPath | Utilities | from __future__ import annotations import datetime import http.client |
| **connectionpool.py** | $escapedPath | Utilities | from __future__ import annotations import errno import logging |
| **__init__.py** | $escapedPath | Utilities |  |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations import urllib3.connection from ...connectionpool import HTTPConnectionPool, HTTPSConnectionPool |
| **connection.py** | $escapedPath | Utilities | from __future__ import annotations import os import typing |
| **fetch.py** | $escapedPath | Utilities | """ Support for streaming http requests in emscripten. A few caveats - |
| **request.py** | $escapedPath | Utilities | from __future__ import annotations from dataclasses import dataclass, field from ..._base_connection import _TYPE_BODY |
| **response.py** | $escapedPath | Utilities | from __future__ import annotations import json as _json import logging |
| **pyopenssl.py** | $escapedPath | Utilities | """ Module for using pyOpenSSL as a TLS backend. This module was relevant before the standard library ``ssl`` module supported SNI, but now that we've dropped |
| **socks.py** | $escapedPath | Utilities | """ This module contains provisional support for SOCKS proxies from within urllib3. This module supports SOCKS4, SOCKS4A (an extension of SOCKS4), and |
| **exceptions.py** | $escapedPath | Utilities | from __future__ import annotations import socket import typing |
| **fields.py** | $escapedPath | Utilities | from __future__ import annotations import email.utils import mimetypes |
| **filepost.py** | $escapedPath | Utilities | from __future__ import annotations import binascii import codecs |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations from importlib.metadata import version __all__ = [ |
| **connection.py** | $escapedPath | Utilities | from __future__ import annotations import logging import re |
| **probe.py** | $escapedPath | Utilities | from __future__ import annotations import threading class _HTTP2ProbeCache: |
| **poolmanager.py** | $escapedPath | Utilities | from __future__ import annotations import functools import logging |
| **response.py** | $escapedPath | Utilities | from __future__ import annotations import collections import io |
| **__init__.py** | $escapedPath | Utilities | # For backwards compatibility, provide imports that used to be here. from __future__ import annotations from .connection import is_connection_dropped |
| **connection.py** | $escapedPath | Utilities | from __future__ import annotations import socket import typing |
| **proxy.py** | $escapedPath | Utilities | from __future__ import annotations import typing from .url import Url |
| **request.py** | $escapedPath | Utilities | from __future__ import annotations import io import sys |
| **response.py** | $escapedPath | Utilities | from __future__ import annotations import http.client as httplib from email.errors import MultipartInvariantViolationDefect, StartBoundaryNotFoundDefect |
| **retry.py** | $escapedPath | Utilities | from __future__ import annotations import email import logging |
| **ssl_.py** | $escapedPath | Utilities | from __future__ import annotations import hashlib import hmac |
| **ssl_match_hostname.py** | $escapedPath | Utilities | """The match_hostname() function from Python 3.5, essential when using SSL.""" # Note: This file is under the PSF license as the code comes from the python #... |
| **ssltransport.py** | $escapedPath | Utilities | from __future__ import annotations import io import socket |
| **timeout.py** | $escapedPath | Utilities | from __future__ import annotations import time import typing |
| **url.py** | $escapedPath | Utilities | from __future__ import annotations import re import typing |
| **util.py** | $escapedPath | Utilities | from __future__ import annotations import typing from types import TracebackType |
| **wait.py** | $escapedPath | Utilities | from __future__ import annotations import select import socket |
| **Safe-PythonExec.ps1** | $escapedPath | Utilities | <#      Safe-PythonExec.ps1     -------------------- |
| **analyze_14_9.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **analyze_categories_deep.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.analytics.analyze_categories_deep. """ |
| **analyze_extended_core.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.analytics.analyze_extended_core. """ |
| **analyze_honeywell_core.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.analytics.analyze_honeywell_core. """ |
| **analyze_remaining_lots.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.analytics.analyze_remaining_lots. """ |
| **analyze_top_50_deep.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.analytics.analyze_top_50_deep. """ |
| **auto_setup_cursor_vpn.ps1** | $escapedPath | Utilities | [CmdletBinding()] param() Set-StrictMode -Version Latest |
| **analyze_tbank_json.py** | $escapedPath | Analytics | """ РЈС‚РёР»РёС‚Р° РґР»СЏ Р±РµР·РѕРїР°СЃРЅРѕРіРѕ Р°РЅР°Р»РёР·Р° РєСЂСѓРїРЅС‹С… JSON-РѕС‚РІРµС‚РѕРІ T-Bank. РЎРєСЂРёРїС‚ РІС‹РІРѕРґРёС‚ С‚РѕР»СЊРєРѕ СЃРІРѕРґР... |
| **fetch_tbank.py** | $escapedPath | Utilities | """ Р—Р°РїСЂР°С€РёРІР°РµС‚ СЃРІРµР¶РёР№ СЃРїРёСЃРѕРє РЅР°РєР»Р°РґРЅС‹С… РёР· T-Bank Рё СЃРѕС…СЂР°РЅСЏРµС‚ РѕС‚РІРµС‚ РІ diagnostics/. """ |
| **list_tbank_env.py** | $escapedPath | Utilities | from pathlib import Path def main() -> None:     env_path = Path(".env") |
| **probe_tbank_invoices.ps1** | $escapedPath | Utilities | param(     [string]$BaseUrl ) |
| **test_tbank_api.sh** | $escapedPath | Diagnostics | #!/bin/bash set -euo pipefail ENV_FILE="/root/tbank-env" |
| **test_tbank_consignments.py** | $escapedPath | Diagnostics | """Р”РёР°РіРЅРѕСЃС‚РёРєР° СЌРЅРґРїРѕРёРЅС‚РѕРІ T-Bank РґР»СЏ РїРѕР»СѓС‡РµРЅРёСЏ С‚РѕРІР°СЂРЅС‹С… РЅР°РєР»Р°РґРЅС‹С….""" from __future__ import annotations im... |
| **test_tbank_invoices.py** | $escapedPath | Diagnostics | """Р”РёР°РіРЅРѕСЃС‚РёРєР° СЌРЅРґРїРѕРёРЅС‚Р° T-Bank /v1/invoices.""" from __future__ import annotations import json |
| **Test-TBankAPI.ps1** | $escapedPath | Utilities | param(     [string]$Server = 'root@216.9.227.124',     [string]$RemotePath = '/root/test_tbank_api.sh', |
| **chatgpt_vps_test.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРёР№ С‚РµСЃС‚ СЃС‚Р°Р±РёР»СЊРЅРѕСЃС‚Рё ChatGPT РЅР° VPS |
| **check_my_top5.py** | $escapedPath | Diagnostics | """ Compatibility shim for scripts.diagnostics.check_my_top5. """ |
| **compare_cores.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.analytics.compare_cores. """ |
| **compare_cores_v3.py** | $escapedPath | Analytics | """ Compatibility shim for scripts.archive.compare_cores_v3. """ |
| **deep_analyze_14_16.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.analytics.deep_analyze_14_16. """ |
| **extract_honeywell_core.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.analytics.extract_honeywell_core. """ |
| **extract_honeywell_core_v2.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.archive.extract_honeywell_core_v2. """ |
| **find_global_top5.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.analytics.find_global_top5. """ |
| **Lint-ConfigFiles.ps1** | $escapedPath | Infrastructure | Set-StrictMode -Version Latest $ErrorActionPreference = 'Stop' $workspaceRoot = Resolve-Path "$PSScriptRoot/../.." |
| **Validate-SshUsage.ps1** | $escapedPath | Infrastructure | param(     [string]$LogPattern = "*.log" ) |
| **Check-Tunnel.ps1** | $escapedPath | Infrastructure | <# .SYNOPSIS     РџСЂРѕРІРµСЂСЏРµС‚ РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ СЃРµС‚Рё С‡РµСЂРµР· Р°РєС‚РёРІРЅС‹Р№ С‚СѓРЅРЅРµР»СЊ. |
| **Start-SSH-Tunnel.ps1** | $escapedPath | Infrastructure | <# .SYNOPSIS     Р—Р°РїСѓСЃРєР°РµС‚ SSH SOCKS5 С‚СѓРЅРЅРµР»СЊ РІ С„РѕРЅРѕРІРѕРј СЂРµР¶РёРјРµ. |
| **Start-Xray.ps1** | $escapedPath | Infrastructure | <# .SYNOPSIS     Р—Р°РїСѓСЃРєР°РµС‚ Xray РІ С„РѕРЅРѕРІРѕРј СЂРµР¶РёРјРµ Р±РµР· Р±Р»РѕРєРёСЂРѕРІРєРё С‚РµСЂРјРёРЅР°Р»Р°. |
| **active_context_loader.ps1** | $escapedPath | Infrastructure | <# active_context_loader.ps1 РЎРѕР±РёСЂР°РµС‚ РјРёРЅРёРјР°Р»СЊРЅС‹Р№, Р±РµР·РѕРїР°СЃРЅС‹Р№ Рё РєРѕРЅС‚СЂРѕР»РёСЂСѓРµРјС‹Р№ РєРѕРЅС‚РµРєСЃС‚ РїСЂРѕРµРєС‚Р° |
| **backup_shopware.sh** | $escapedPath | Infrastructure | #!/bin/bash # backup_shopware.sh - РџРѕР»РЅС‹Р№ Р±СЌРєР°Рї Shopware 6 РїРµСЂРµРґ РѕР±РЅРѕРІР»РµРЅРёРµРј set -euo pipefail |
| **Clean-Workspace.ps1** | $escapedPath | Infrastructure | param(     [int]$DaysToKeep = 7 ) |
| **deploy-gateway.sh** | $escapedPath | Infrastructure | #!/bin/bash # РЎРєСЂРёРїС‚ СЂР°Р·РІС‘СЂС‚С‹РІР°РЅРёСЏ T-Bank Webhook Gateway РЅР° RU-VPS # РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: ./deploy-gateway.sh |
| **deploy-wg-config.sh** | $escapedPath | Infrastructure | #!/bin/bash # Deploy WireGuard configuration safely. # |
| **deploy-xray-config.sh** | $escapedPath | Infrastructure | #!/bin/bash set -euo pipefail CONFIG_FILE="${1:-}" |
| **Initialize-Session.ps1** | $escapedPath | Infrastructure | <# Initialize-Session.ps1 Р—Р°РіСЂСѓР¶Р°РµС‚ РєСЂР°С‚РєРёР№ РєРѕРЅС‚РµРєСЃС‚ РїСЂРѕРµРєС‚Р° Biretos Automation РїСЂРё СЃС‚Р°СЂС‚Рµ СЃРµСЃСЃРёРё. |
| **install-xray.sh** | $escapedPath | Infrastructure | #!/bin/bash set -euo pipefail LOG_FILE="/tmp/install_xray.log" |
| **Invoke-SafeScp.ps1** | $escapedPath | Infrastructure | <# .SYNOPSIS     Safe SCP wrapper with centralized config, logging, and timeouts. |
| **Invoke-SafeSsh.ps1** | $escapedPath | Infrastructure | <# .SYNOPSIS     Safe SSH wrapper with centralized config, logging, and timeouts. |
| **non_interactive_mysql.sh** | $escapedPath | Infrastructure | #!/usr/bin/env bash # Non-interactive MySQL РєРѕРјР°РЅРґС‹ РґР»СЏ Shopware # РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: |
| **shopware_diagnostic.sh** | $escapedPath | Infrastructure | #!/usr/bin/env bash # Non-interactive РґРёР°РіРЅРѕСЃС‚РёРєР° Shopware С‡РµСЂРµР· SSH # РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: ./shopware_diagnostic.sh |
| **shopware_mysql_query.py** | $escapedPath | Infrastructure | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **ssh_mysql_query.sh** | $escapedPath | Infrastructure | #!/usr/bin/env bash # Р’С‹РїРѕР»РЅРµРЅРёРµ MySQL Р·Р°РїСЂРѕСЃР° С‡РµСЂРµР· SSH (non-interactive) # РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: ./ssh_mysql_query.sh "SELECT *... |
| **Update-ProjectStatus.ps1** | $escapedPath | Infrastructure | <# Update-ProjectStatus.ps1 РћР±РЅРѕРІР»СЏРµС‚ PROJECT_STATUS.md РЅР° РѕСЃРЅРѕРІРµ С‚РµРєСѓС‰РµР№ РёРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂС‹ Рё AI-Р»РѕРіРѕРІ. |
| **analyze_duplicates.py** | $escapedPath | Migration | """ РђРЅР°Р»РёР· РґСѓР±Р»РёСЂРѕРІР°РЅРЅС‹С… Property Groups Рё СЃРІРѕР№СЃС‚РІ С‚РѕРІР°СЂРѕРІ РІ Shopware 6. РЎРєСЂРёРїС‚ Р°РЅР°Р»РёР·РёСЂСѓРµС‚: |
| **analyze_product_properties.py** | $escapedPath | Migration | """ РђРЅР°Р»РёР· С…Р°СЂР°РєС‚РµСЂРёСЃС‚РёРє С‚РѕРІР°СЂР° РёР· InSales snapshot Рё СЃСЂР°РІРЅРµРЅРёРµ СЃ Shopware """ |
| **apply_property_groups_visibility_matrix.py** | $escapedPath | Migration | """ РџСЂРёРјРµРЅРµРЅРёРµ РєР°РЅРѕРЅРёС‡РµСЃРєРѕР№ РјР°С‚СЂРёС†С‹ РІРёРґРёРјРѕСЃС‚Рё Property Groups РІ Shopware 6. РљР›РђРЎРЎ A вЂ” СЃРєСЂС‹С‚СЊ РїРѕР»РЅРѕСЃ... |
| **check_imported_product.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂСЏРµС‚ РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹Р№ С‚РѕРІР°СЂ РІ Shopware """ |
| **check_insales_api.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **check_pdp_properties.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **check_shopware_categories.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂСЏРµС‚, РєР°РєРёРµ РєР°С‚РµРіРѕСЂРёРё РђРІРёР°Р·Р°РїС‡Р°СЃС‚Рё РµСЃС‚СЊ РІ Shopware """ |
| **cleanup_product_properties.py** | $escapedPath | Migration | """ РћС‡РёСЃС‚РєР° РґСѓР±Р»РёСЂРѕРІР°РЅРЅС‹С… СЃРІРѕР№СЃС‚РІ Сѓ С‚РѕРІР°СЂРѕРІ РІ Shopware 6. РЎРєСЂРёРїС‚ РЅР°С…РѕРґРёС‚ С‚РѕРІР°СЂС‹ СЃ РґСѓР±Р»РёСЂРѕРІР°Р... |
| **create_properties_override_plugin.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **deploy_hide_properties_plugin.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """Р Р°Р·РІС‘СЂС‚С‹РІР°РЅРёРµ РїР»Р°РіРёРЅР° HideUnwantedProperties РЅР° СЃРµСЂРІРµСЂ Shopware.""" |
| **disable_old_filters.py** | $escapedPath | Migration | """ РћС‚РєР»СЋС‡РµРЅРёРµ С„РёР»СЊС‚СЂРѕРІ Сѓ СЃС‚Р°СЂС‹С… Property Groups РІ Shopware 6. РЎРєСЂРёРїС‚ РЅР°С…РѕРґРёС‚ Property Groups СЃ filterable=true, РєРѕ... |
| **find_and_modify_twig.ps1** | $escapedPath | Migration | # РџРѕРёСЃРє Рё РјРѕРґРёС„РёРєР°С†РёСЏ Twig-С€Р°Р±Р»РѕРЅР° СЃРІРѕР№СЃС‚РІ С‚РѕРІР°СЂР° РЅР° СЃРµСЂРІРµСЂРµ Shopware param(     [string]$ServerName = "biretos... |
| **find_product_with_category.py** | $escapedPath | Migration | import csv import json from pathlib import Path |
| **find_properties_template.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **find_twig_template.sh** | $escapedPath | Migration | #!/bin/bash # РџРѕРёСЃРє Twig-С€Р°Р±Р»РѕРЅР° СЃРІРѕР№СЃС‚РІ С‚РѕРІР°СЂР° РЅР° СЃРµСЂРІРµСЂРµ Shopware # Р’РѕР·РјРѕР¶РЅС‹Рµ РїСѓС‚Рё |
| **get_properties_template.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **get_theme_info.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **hide_properties_pdp.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **modify_properties_twig.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **recon_shopware_path.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **reference_product_import.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **category_invariants.py** | $escapedPath | Migration | """ CATEGORY INVARIANTS - Р–С‘СЃС‚РєРёРµ РїСЂР°РІРёР»Р° РґР»СЏ РєР°С‚РµРіРѕСЂРёР№. Р­С‚Рё РёРЅРІР°СЂРёР°РЅС‚С‹ РґРѕР»Р¶РЅС‹ СЃРѕР±Р»СЋРґР°С‚СЊСЃСЏ Р’РЎР•Р“Р”... |
| **analyze_category_issues.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РђРЅР°Р»РёР· РєР°С‚РµРіРѕСЂРёР№ РІ products.ndjson: |
| **analyze_mapping_final.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅС‹Р№ Р°РЅР°Р»РёР·: РїСЂРѕРІРµСЂРєР° СЂРµР°Р»СЊРЅС‹С… С‚РѕРІР°СЂРѕРІ РІ Shopware Рё РёС… СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёРµ. """ |
| **apply_category_cleanup.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ Р‘РµР·РѕРїР°СЃРЅР°СЏ РѕС‡РёСЃС‚РєР° РєР°С‚РµРіРѕСЂРёР№ С‚РѕРІР°СЂРѕРІ РїРѕ РѕС‚С‡С‘С‚Сѓ category_cleanup_audit.md. |
| **audit_category_cleanup.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РђСѓРґРёС‚ РєР°С‚РµРіРѕСЂРёР№ РІ Shopware РґР»СЏ Р±РµР·РѕРїР°СЃРЅРѕРіРѕ РёСЃРїСЂР°РІР»РµРЅРёСЏ. |
| **audit_system.py** | $escapedPath | Migration | """ РђСѓРґРёС‚ СЃРёСЃС‚РµРјС‹ Shopware 6: Manufacturers, Marketplace Price Rules, Products. РўРѕР»СЊРєРѕ С‡С‚РµРЅРёРµ РґР°РЅРЅС‹С…, Р±РµР· РёР·РјРµРЅРµРЅРёР№. |
| **auto_map_categories.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **canon_registry.py** | $escapedPath | Migration | from __future__ import annotations import logging from datetime import datetime, timezone |
| **category_utils.py** | $escapedPath | Migration | from __future__ import annotations import re from typing import Any, Dict, List, Optional |
| **check_after_update.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° С‚РѕРІР°СЂР° СЃСЂР°Р·Сѓ РїРѕСЃР»Рµ РѕР±РЅРѕРІР»РµРЅРёСЏ""" import json import time |
| **check_barcode_api.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **check_category_logic.py** | $escapedPath | Migration | """ Dry-run РїСЂРѕРІРµСЂРєР° РєР°РЅРѕРЅРёС‡РµСЃРєРѕР№ Р»РѕРіРёРєРё РєР°С‚РµРіРѕСЂРёР№ РІ Shopware 6. РџСЂРѕРІРµСЂСЏРµС‚: |
| **check_config_thumbnails.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РєРѕРЅС„РёРіСѓСЂР°С†РёРё thumbnail sizes""" import json import sys |
| **check_cover_in_media.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import json |
| **check_folder_resolution.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° СЂР°Р·СЂРµС€РµРЅРёСЏ РїР°РїРєРё РІ СЂРµР°Р»СЊРЅРѕРј РёРјРїРѕСЂС‚Рµ""" import json import sys |
| **check_imported_100.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹С… 100 С‚РѕРІР°СЂРѕРІ.""" import sys |
| **check_imported_products.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РїРѕСЃР»РµРґРЅРёС… РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹С… С‚РѕРІР°СЂРѕРІ""" import json from pathlib import Path |
| **check_listing_sql.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° product_media Рё product_listing_index С‡РµСЂРµР· SQL""" |
| **check_listing_sql_server.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° product_media Рё product_listing_index С‡РµСЂРµР· SQL РЅР° СЃРµСЂРІРµСЂРµ""" |
| **check_media_sample.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РЅРµСЃРєРѕР»СЊРєРёС… media РґР»СЏ РґРёР°РіРЅРѕСЃС‚РёРєРё""" import json from pathlib import Path |
| **check_media_structure.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° СЃС‚СЂСѓРєС‚СѓСЂС‹ РјРµРґРёР° РґР»СЏ РѕРїСЂРµРґРµР»РµРЅРёСЏ РїСЂР°РІРёР»СЊРЅРѕРіРѕ РїРѕР»СЏ""" import json import sys |
| **check_normalization.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё Shopware.""" import sys from pathlib import Path |
| **check_price2.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° price2 РІ snapshot""" import json from pathlib import Path |
| **check_price2_for_imported.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° price2 РґР»СЏ РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹С… С‚РѕРІР°СЂРѕРІ""" import json from pathlib import Path |
| **check_price2_for_sku.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° price2 РґР»СЏ РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ SKU""" import json from pathlib import Path |
| **check_product_details.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РґРµС‚Р°Р»РµР№ С‚РѕРІР°СЂР°""" import json from pathlib import Path |
| **check_product_media_structure.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° СЃС‚СЂСѓРєС‚СѓСЂС‹ РјРµРґРёР° РІ РѕС‚РІРµС‚Рµ API""" |
| **check_product_structure.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° СЃС‚СЂСѓРєС‚СѓСЂС‹ РѕС‚РІРµС‚Р° API РґР»СЏ С‚РѕРІР°СЂР°""" |
| **check_real_product_category_assignments.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РџСЂРѕРІРµСЂРєР° СЂРµР°Р»СЊРЅС‹С… product-category assignments РґР»СЏ С‚РѕРІР°СЂР°. |
| **check_real_products.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂРєР° СЂРµР°Р»СЊРЅС‹С… С‚РѕРІР°СЂРѕРІ РІ Shopware РґР»СЏ РїРѕРёСЃРєР° РєР»СЋС‡Р° СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёСЏ. """ |
| **check_recent_media.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РїРѕСЃР»РµРґРЅРёС… Р·Р°РіСЂСѓР¶РµРЅРЅС‹С… РјРµРґРёР° СЃ РґРµС‚Р°Р»СЏРјРё""" import json import sys |
| **check_recent_products.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РїРѕСЃР»РµРґРЅРёС… СЃРѕР·РґР°РЅРЅС‹С… С‚РѕРІР°СЂРѕРІ""" import json from pathlib import Path |
| **check_rules_detail.py** | $escapedPath | Migration | """Р”РµС‚Р°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° Marketplace Price rules.""" import sys from pathlib import Path |
| **check_sku_in_snapshot.py** | $escapedPath | Migration | #!/usr/bin/env python3 import json import sys |
| **check_specific_product.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ С‚РѕРІР°СЂР°""" import json from pathlib import Path |
| **check_specific_products.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂРєР° РєРѕРЅРєСЂРµС‚РЅС‹С… С‚РѕРІР°СЂРѕРІ РїРѕ SKU """ |
| **check_taxes.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РЅР°Р»РѕРіРѕРІС‹С… СЃС‚Р°РІРѕРє РІ Shopware""" import json import sys |
| **check_thumbnail_sizes.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° thumbnail sizes РІ РїР°РїРєР°С… РјРµРґРёР°""" import json import sys |
| **check_thumbnail_sizes_in_config.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import subprocess |
| **cleanup_duplicate_categories.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РЈСЃС‚СЂР°РЅРµРЅРёРµ РґСѓР±Р»РёСЂСѓСЋС‰РёС… РєР°С‚РµРіРѕСЂРёР№ "РђРІРёР°Р·Р°РїС‡Р°СЃС‚Рё" РІ Shopware.""" from __future__ import an... |
| **cleanup_orphan_media.py** | $escapedPath | Migration | """ РћС‡РёСЃС‚РєР° Shopware РѕС‚ orphan media (РјРµРґРёР°-С„Р°Р№Р»РѕРІ Р±РµР· СЃРІСЏР·РµР№) """ |
| **__init__.py** | $escapedPath | Migration | from .insales_client import InsalesClient, InsalesClientError, InsalesConfig from .shopware_client import ShopwareClient, ShopwareClientError, ShopwareConfig... |
| **insales_client.py** | $escapedPath | Migration | from __future__ import annotations import logging import os |
| **shopware_client.py** | $escapedPath | Migration | from __future__ import annotations import csv import logging |
| **count_products.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџРѕРґСЃС‡РµС‚ С‚РѕРІР°СЂРѕРІ РІ Shopware.""" import sys |
| **create_sql_script.py** | $escapedPath | Migration | """РЎРѕР·РґР°РЅРёРµ Python СЃРєСЂРёРїС‚Р° РЅР° СЃРµСЂРІРµСЂРµ РґР»СЏ РІС‹РїРѕР»РЅРµРЅРёСЏ SQL""" script_content = '''#!/usr/bin/env python3 import os |
| **debug_media_folder_assignment.py** | $escapedPath | Migration | """Р”РёР°РіРЅРѕСЃС‚РёРєР° РїСЂРѕР±Р»РµРјС‹ СЃ СЃРѕС…СЂР°РЅРµРЅРёРµРј mediaFolderId Рё configurationId""" import json import sys |
| **debug_media_folders.py** | $escapedPath | Migration | """РЎРєСЂРёРїС‚ РґР»СЏ РїСЂРѕРІРµСЂРєРё РјРµРґРёР°-РїР°РїРѕРє Рё РєРѕРЅС„РёРіСѓСЂР°С†РёР№ РІ Shopware""" import json import sys |
| **debug_product_visibility.py** | $escapedPath | Migration | """ РћС‚Р»Р°РґРѕС‡РЅС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РїСЂРѕРІРµСЂРєРё product_visibility С‚РѕРІР°СЂРѕРІ. РџРѕРєР°Р·С‹РІР°РµС‚ РґРµС‚Р°Р»СЊРЅСѓСЋ РёРЅС„РѕСЂРјР°С†РёСЋ... |
| **debug_thumbnail_skip.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import subprocess |
| **delete_non_canonical_products.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РњР°СЃСЃРѕРІРѕРµ СѓРґР°Р»РµРЅРёРµ РЅРµРєР°РЅРѕРЅРёС‡РЅС‹С… С‚РѕРІР°СЂРѕРІ РёР· Shopware. |
| **diag_insales_cdn.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **diag_insales_images_and_update.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **diagnose_categories_state.py** | $escapedPath | Migration | """ Р§РРЎРўРђРЇ Р”РРђР“РќРћРЎРўРРљРђ СЃРѕСЃС‚РѕСЏРЅРёСЏ РєР°С‚РµРіРѕСЂРёР№ РІ Shopware 6. РўРћР›Р¬РљРћ С‡С‚РµРЅРёРµ РґР°РЅРЅС‹С…, РќРРљРђРљРРҐ РёР·РјРµР... |
| **diagnose_final.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **diagnose_listing_images.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **dump_full_insales.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **enrich_existing_products.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ ENRICH-РїР°Р№РїР»Р°Р№РЅ РґР»СЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… С‚РѕРІР°СЂРѕРІ РІ Shopware. |
| **execute_sql_fix.py** | $escapedPath | Migration | """Р’С‹РїРѕР»РЅРµРЅРёРµ SQL С„РёРєСЃР° РЅР° СЃРµСЂРІРµСЂРµ С‡РµСЂРµР· SSH""" import subprocess import sys |
| **execute_sql_on_server.py** | $escapedPath | Migration | #!/usr/bin/env python3 import os import pymysql |
| **fill_barcode_mass.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **final_check_sku_barcode.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° РёРјРїРѕСЂС‚Р° SKU (productNumber) Рё С€С‚СЂРёС…-РєРѕРґР° РЅР° С‚РµСЃС‚РѕРІС‹С… 10 С‚РѕРІР°СЂР°С… |
| **final_validation_update.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **final_verification.py** | $escapedPath | Migration | """Р¤РёРЅР°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° Marketplace С†РµРЅ""" import json from pathlib import Path |
| **find_10_new_products_for_dimensions_test.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РќР°С…РѕРґРёС‚ 10 РЅРѕРІС‹С… С‚РѕРІР°СЂРѕРІ РёР· СЂР°Р·РЅС‹С… parent-РєР°С‚РµРіРѕСЂРёР№ РґР»СЏ РїСЂРѕРІРµСЂРєРё dimensions Рё weight. |
| **find_and_import_new_product.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РќР°С…РѕРґРёС‚ РЅРѕРІС‹Р№ SKU РёР· snapshot Рё РІС‹РїРѕР»РЅСЏРµС‚ РєРѕРЅС‚СЂРѕР»СЊРЅС‹Р№ РёРјРїРѕСЂС‚. |
| **find_mapping_key.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅС‹Р№ Р°РЅР°Р»РёР· РєР»СЋС‡Р° СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёСЏ С‚РѕРІР°СЂРѕРІ. РџСЂРѕРІРµСЂСЏРµС‚ РІСЃРµ РІРѕР·РјРѕР¶РЅС‹Рµ РІР°СЂРёР°РЅС‚С‹. |
| **find_product_for_test.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РќР°С…РѕРґРёС‚ С‚РѕРІР°СЂ РґР»СЏ С‚РµСЃС‚Р° РїРµСЂРµСЃРѕР·РґР°РЅРёСЏ РјРµРґРёР°""" |
| **find_product_mapping.py** | $escapedPath | Migration | """ РџРѕРёСЃРє СЂРµР°Р»СЊРЅРѕРіРѕ РєР»СЋС‡Р° СЃРѕРїРѕСЃС‚Р°РІР»РµРЅРёСЏ С‚РѕРІР°СЂРѕРІ InSales в†’ Shopware. РџСЂРѕРІРµСЂСЏРµС‚: |
| **find_products.py** | $escapedPath | Migration | """Р’СЂРµРјРµРЅРЅС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РїРѕРёСЃРєР° С‚РѕРІР°СЂРѕРІ СЃ РїРѕР»РЅС‹РјРё РґР°РЅРЅС‹РјРё""" import json import sys |
| **find_products_with_dimensions_weight.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РќР°С…РѕРґРёС‚ С‚РѕРІР°СЂС‹ СЃ Р·Р°РґР°РЅРЅС‹РјРё СЂР°Р·РјРµСЂР°РјРё Рё РІРµСЃРѕРј РІ snapshot. |
| **find_sku_field.py** | $escapedPath | Migration | """ РўРѕС‡РЅРѕРµ РѕРїСЂРµРґРµР»РµРЅРёРµ РїРѕР»СЏ Shopware, РіРґРµ С…СЂР°РЅРёС‚СЃСЏ InSales SKU (РђСЂС‚РёРєСѓР»). """ |
| **fix_all_folders_config.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import subprocess |
| **fix_barcode_field_display.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **fix_category_seo_and_finalize.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **fix_default_folder.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import subprocess |
| **fix_existing_products_media.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **fix_folder_config_sql.py** | $escapedPath | Migration | """РСЃРїСЂР°РІР»РµРЅРёРµ СЃРІСЏР·Рё РїР°РїРєРё СЃ РєРѕРЅС„РёРіСѓСЂР°С†РёРµР№ С‡РµСЂРµР· SQL""" import json import sys |
| **fix_leaf_categories.py** | $escapedPath | Migration | """ РСЃРїСЂР°РІР»РµРЅРёРµ Р»РѕРіРёРєРё РЅР°Р·РЅР°С‡РµРЅРёСЏ РєР°С‚РµРіРѕСЂРёР№ РїСЂРё РёРјРїРѕСЂС‚Рµ. Р“Р°СЂР°РЅС‚РёСЂСѓРµС‚, С‡С‚Рѕ С‚РѕРІР°СЂС‹ РїСЂРёРІСЏ... |
| **fix_product_visibility.py** | $escapedPath | Migration | """ РСЃРїСЂР°РІР»РµРЅРёРµ product_visibility РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ С‚РѕРІР°СЂРѕРІ РІ leaf-РєР°С‚РµРіРѕСЂРёСЏС… Shopware 6. РџСЂРѕР±Р»РµРјР°: РўРѕРІР... |
| **fix_sales_channel_entry_point.py** | $escapedPath | Migration | """ РСЃРїСЂР°РІР»РµРЅРёРµ entry point РґР»СЏ Sales Channel. Р’РђР–РќРћ: ROOT_NAV - С‚РµС…РЅРёС‡РµСЃРєР°СЏ РєР°С‚РµРіРѕСЂРёСЏ РЅР°РІРёРіР°С†РёРё. |
| **fix_shopware_category_structure.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ РєР°С‚РµРіРѕСЂРёР№ Shopware СЃ РєР°РЅРѕРЅРёС‡РµСЃРєРѕР№ СЃС‚СЂСѓРєС‚СѓСЂРѕР№ InSales. РћСЃРЅРѕРІРЅС‹Рµ Р... |
| **fix_thumbnail_config.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- import subprocess |
| **force_remove_product_categories_direct.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РџСЂСЏРјРѕРµ СѓРґР°Р»РµРЅРёРµ РєР°С‚РµРіРѕСЂРёР№ С‚РѕРІР°СЂР° С‡РµСЂРµР· SQL (РґР»СЏ С‚РµСЃС‚РёСЂРѕРІР°РЅРёСЏ). |
| **force_update_canonical.py** | $escapedPath | Migration | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅС‹Р№ UPDATE С‚РѕРІР°СЂР° СЃ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµРј РљРћР Р Р•РљРўРќР«РҐ API Shopware 6. РЁРђР“ 1: Visibilities (DELETE + PO... |
| **force_update_product.py** | $escapedPath | Migration | """ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅС‹Р№ UPDATE С‚РѕРІР°СЂР° РґР»СЏ РїСЂРёРІРµРґРµРЅРёСЏ РІ РєР°РЅРѕРЅРёС‡РµСЃРєРѕРµ СЃРѕСЃС‚РѕСЏРЅРёРµ. РСЃРїСЂР°РІР»СЏРµС‚: ean, v... |
| **full_import.py** | $escapedPath | Migration | """ РџРѕР»РЅС‹Р№ РёРјРїРѕСЂС‚ РІСЃРµС… С‚РѕРІР°СЂРѕРІ РёР· CSV РІ Shopware СЃ РѕР±СЂР°Р±РѕС‚РєРѕР№ РґСѓР±Р»РёРєР°С‚РѕРІ """ |
| **generate_500_import_report.py** | $escapedPath | Migration | #!/usr/bin/env python3 """Р“РµРЅРµСЂР°С†РёСЏ РѕС‚С‡РµС‚Р° РѕР± РёРјРїРѕСЂС‚Рµ 500 С‚РѕРІР°СЂРѕРІ.""" import json |
| **generate_shopware_csv.py** | $escapedPath | Migration | from __future__ import annotations import argparse import csv |
| **category_canonical_guard.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° СЃРѕРѕС‚РІРµС‚СЃС‚РІРёСЏ РєР°С‚РµРіРѕСЂРёР№ Shopware РєР°РЅРѕРЅРёС‡РµСЃРєРѕР№ СЃС‚СЂСѓРєС‚СѓСЂРµ InSales.""" from ... |
| **properties_pipeline_guard.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° РІРєР»СЋС‡РµРЅРёСЏ properties РІ pipeline Рё РІР°Р»РёРґР°С†РёСЏ payload.""" from __future__ import annotations |
| **variants_canonical_guard.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° СЃРѕРѕС‚РІРµС‚СЃС‚РІРёСЏ variants РєР°РЅРѕРЅРёС‡РµСЃРєРѕР№ СЃС‚СЂСѓРєС‚СѓСЂРµ: 1 С‚РѕРІР°СЂ = 1 РІР°СЂРёР°РЅС‚."""... |
| **import_all_single_variant.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РРјРїРѕСЂС‚ РІСЃРµС… РѕСЃС‚Р°РІС€РёС…СЃСЏ С‚РѕРІР°СЂРѕРІ СЃ 1 РІР°СЂРёР°РЅС‚РѕРј РёР· snapshot. |
| **import_batch.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РРјРїРѕСЂС‚ С‚РѕРІР°СЂРѕРІ РїРѕ Р±Р°С‚С‡Р°Рј.""" import json |
| **__init__.py** | $escapedPath | Migration | from __future__ import annotations from dataclasses import dataclass, field from enum import Enum |
| **categories.py** | $escapedPath | Migration | from __future__ import annotations from typing import Any, Dict, List, Optional from clients import ShopwareClient |
| **manufacturer.py** | $escapedPath | Migration | from __future__ import annotations from typing import Any, Dict, Optional from canon_registry import CanonRegistry |
| **media.py** | $escapedPath | Migration | from __future__ import annotations import io import os |
| **prices.py** | $escapedPath | Migration | from __future__ import annotations from typing import Any, Dict from canon_registry import CanonRegistry |
| **properties.py** | $escapedPath | Migration | from __future__ import annotations import uuid from typing import Any, Dict, List |
| **skeleton.py** | $escapedPath | Migration | from __future__ import annotations import uuid from typing import Any, Dict, Optional |
| **verify.py** | $escapedPath | Migration | from __future__ import annotations from typing import Any, Dict from import_steps import ProductImportState, StepState |
| **visibilities.py** | $escapedPath | Migration | from __future__ import annotations from typing import Any, Dict from clients import ShopwareClient |
| **import_utils.py** | $escapedPath | Migration | from __future__ import annotations import json from pathlib import Path |
| **inspect_insales.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **migrate_categories.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **migrate_properties.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **normalize_entities.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **normalize_system.py** | $escapedPath | Migration | """ РќРѕСЂРјР°Р»РёР·Р°С†РёСЏ СЃРёСЃС‚РµРјС‹ Shopware 6: Manufacturers Рё Marketplace Price Rules. РџСЂРёРІРµРґРµРЅРёРµ Рє РєР°РЅРѕРЅРёС‡РµСЃРєРѕРјСѓ СЃРѕСЃС‚... |
| **pipeline_import.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **preflight_check.py** | $escapedPath | Migration | """ PRE-FLIGHT CHECK РґР»СЏ РІР°Р»РёРґР°С†РёРё СЃРєРµР»РµС‚Р° РїСЂРѕРµРєС‚Р° РїРµСЂРµРґ production-РёРјРїРѕСЂС‚РѕРј С‚РѕРІР°СЂРѕРІ. Р’РђР–РќРћ: РўРѕР»СЊРєРѕ ... |
| **prepare_sql_fix.py** | $escapedPath | Migration | """РџРѕРґРіРѕС‚РѕРІРєР° SQL С„РёРєСЃР° РґР»СЏ СЃРІСЏР·Рё РїР°РїРєРё СЃ РєРѕРЅС„РёРіСѓСЂР°С†РёРµР№""" import json import sys |
| **product_gap_audit.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ GAP-Р°СѓРґРёС‚ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… С‚РѕРІР°СЂРѕРІ РІ Shopware. |
| **rebind_categories.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ PRODUCTION-GRADE СЃРєСЂРёРїС‚ РґР»СЏ РјР°СЃСЃРѕРІРѕРіРѕ РїРµСЂРµРїСЂРёРІСЏР·С‹РІР°РЅРёСЏ РєР°С‚РµРіРѕСЂРёР№ Сѓ СЃСѓС‰РµСЃС‚РІСѓСЋС... |
| **reconcile_product_categories_from_snapshot.py** | $escapedPath | Migration | """ РЎРєСЂРёРїС‚ РґР»СЏ reconcile РєР°С‚РµРіРѕСЂРёР№ С‚РѕРІР°СЂРѕРІ РїРѕ snapshot InSales. РЈРґР°Р»СЏРµС‚ legacy РєР°С‚РµРіРѕСЂРёРё (С‚Рµ, РєРѕС‚РѕСЂС‹С… РЅР... |
| **recreate_all_product_media.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **recreate_product_leaf_only.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РўРѕС‡РµС‡РЅРѕРµ РїРµСЂРµСЃРѕР·РґР°РЅРёРµ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРіРѕ С‚РѕРІР°СЂР° РґР»СЏ РїРѕР»РЅРѕРіРѕ СЃР±СЂРѕСЃР° legacy produc... |
| **recreate_product_media.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **recreate_product_media_batch.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **reimport_10_categories.py** | $escapedPath | Migration | """ РџРµСЂРµРёРјРїРѕСЂС‚ 10 С‚РѕРІР°СЂРѕРІ СЃ РїСЂРёРјРµРЅРµРЅРёРµРј РёСЃРїСЂР°РІР»РµРЅРЅРѕР№ Р»РѕРіРёРєРё РєР°С‚РµРіРѕСЂРёР№. Р РµР¶РёРј UPDATE, РїСЂРёРјРµР... |
| **reset_shopware_for_test.py** | $escapedPath | Migration | """ РћС‡РёСЃС‚РєР° Shopware 6 РґР»СЏ С‚РµСЃС‚РѕРІРѕРіРѕ РёРјРїРѕСЂС‚Р°. Р’С‹РїРѕР»РЅСЏРµС‚: |
| **restore_marketplace_prices.py** | $escapedPath | Migration | """ Р’РѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ Marketplace С†РµРЅ (price2 РёР· InSales) РІ Shopware 6 С‡РµСЂРµР· rule-based pricing (product.prices). |
| **restore_product_numbers.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **restore_productnumber.py** | $escapedPath | Migration | """ РњР°СЃСЃРѕРІРѕРµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµ productNumber Сѓ С‚РѕРІР°СЂРѕРІ РІ Shopware С‡РµСЂРµР· migration_map.json Рё snapshot InSales. |
| **run_batch_import_10.py** | $escapedPath | Migration | """ Р—Р°РїСѓСЃРє РїСЂРѕР±РЅРѕРіРѕ РёРјРїРѕСЂС‚Р° 10 С‚РѕРІР°СЂРѕРІ. РСЃРїРѕР»СЊР·СѓРµС‚ full_import.py СЃ С„РёР»СЊС‚СЂР°С†РёРµР№ РїРѕ РѕС‚РѕР±СЂР°РЅРЅС‹Рј SKU. |
| **run_batch_import_10_repeat.py** | $escapedPath | Migration | """ РџРѕРІС‚РѕСЂРЅС‹Р№ РёРјРїРѕСЂС‚ С‚РµС… Р¶Рµ 10 С‚РѕРІР°СЂРѕРІ РїРѕСЃР»Рµ РёСЃРїСЂР°РІР»РµРЅРёСЏ Р»РѕРіРёРєРё Marketplace price. """ |
| **run_batch_test_import.py** | $escapedPath | Migration | """ Р—Р°РїСѓСЃРє РїСЂРѕР±РЅРѕРіРѕ РёРјРїРѕСЂС‚Р° 10 С‚РѕРІР°СЂРѕРІ СЃ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРѕР№ РІР°Р»РёРґР°С†РёРµР№. Р’С‹РїРѕР»РЅСЏРµС‚: |
| **safe_audit_cleanup.py** | $escapedPath | Migration | """ Р‘РµР·РѕРїР°СЃРЅС‹Р№ Р°СѓРґРёС‚ Рё РѕС‡РёСЃС‚РєР° РґСѓР±Р»РµР№ РІ СЃРїСЂР°РІРѕС‡РЅРёРєР°С… Shopware 6. РўРѕР»СЊРєРѕ СѓРґР°Р»РµРЅРёРµ РЅРµРёСЃРїРѕР»СЊР·Сѓ... |
| **safe_normalize_shopware.py** | $escapedPath | Migration | """ Р‘РµР·РѕРїР°СЃРЅР°СЏ РЅРѕСЂРјР°Р»РёР·Р°С†РёСЏ Shopware 6 РїРѕСЃР»Рµ РёРјРїРѕСЂС‚Р° InSales. Р’С‹РїРѕР»РЅСЏРµС‚: |
| **select_and_import_100_products.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ Р’С‹Р±РѕСЂ Рё РёРјРїРѕСЂС‚ 100 РЅРѕРІС‹С… С‚РѕРІР°СЂРѕРІ РёР· InSales РІ Shopware |
| **select_test_products.py** | $escapedPath | Migration | """ РћС‚Р±РѕСЂ 10 С‚РѕРІР°СЂРѕРІ РёР· snapshot РґР»СЏ РїСЂРѕР±РЅРѕРіРѕ РёРјРїРѕСЂС‚Р°. РЈСЃР»РѕРІРёСЏ: |
| **setup_marketplace_rule.py** | $escapedPath | Migration | """РЎРѕР·РґР°РЅРёРµ Price Rule РґР»СЏ Marketplace""" import json from pathlib import Path |
| **snapshot_categories.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **snapshot_products.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **sync_properties_from_snapshot.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **sync_shopware_after_category_changes.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ Shopware РїРѕСЃР»Рµ РёР·РјРµРЅРµРЅРёСЏ РєР°С‚РµРіРѕСЂРёР№ С‚РѕРІР°СЂРѕРІ. |
| **test_batch_import_verify.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РўРµСЃС‚РѕРІС‹Р№ РёРјРїРѕСЂС‚ 15 С‚РѕРІР°СЂРѕРІ Рё verify. |
| **test_connections.py** | $escapedPath | Migration | from __future__ import annotations import argparse import json |
| **test_cover_associations.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **test_create_with_marketplace.py** | $escapedPath | Migration | """РўРµСЃС‚ СЃРѕР·РґР°РЅРёСЏ РЅРѕРІРѕРіРѕ С‚РѕРІР°СЂР° СЃ Marketplace С†РµРЅРѕР№""" import json import time |
| **test_final_import.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅС‹Р№ С‚РµСЃС‚РѕРІС‹Р№ РёРјРїРѕСЂС‚ 10 С‚РѕРІР°СЂРѕРІ СЃ РїСЂРѕРІРµСЂРєРѕР№ Marketplace С†РµРЅ """ |
| **test_import.py** | $escapedPath | Migration | from __future__ import annotations import argparse import csv |
| **test_import_verify_10.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РљРѕРЅС‚СЂРѕР»СЊРЅС‹Р№ С‚РµСЃС‚РѕРІС‹Р№ РёРјРїРѕСЂС‚ 10 С‚РѕРІР°СЂРѕРІ Рё verify. |
| **test_marketplace_final.py** | $escapedPath | Migration | """Р¤РёРЅР°Р»СЊРЅС‹Р№ С‚РµСЃС‚ Marketplace С†РµРЅС‹""" import json import time |
| **test_media_upload.py** | $escapedPath | Migration | """РўРµСЃС‚РѕРІС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РїСЂРѕРІРµСЂРєРё Р·Р°РіСЂСѓР·РєРё РјРµРґРёР° РІ РїР°РїРєСѓ""" import json import sys |
| **test_pipeline_import_fresh.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РўРµСЃС‚ РїРѕР»РЅРѕРіРѕ pipeline РёРјРїРѕСЂС‚Р° РЅР° СЃРІРµР¶РµРј С‚РѕРІР°СЂРµ. |
| **test_price_failfast_validation.py** | $escapedPath | Migration | """ РўРµСЃС‚РѕРІС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РІР°Р»РёРґР°С†РёРё fail-fast Р»РѕРіРёРєРё С†РµРЅ. РџСЂРѕРІРµСЂСЏРµС‚, С‡С‚Рѕ: |
| **test_reimport_10.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅС‹Р№ С‚РµСЃС‚РѕРІС‹Р№ РїРµСЂРµРёРјРїРѕСЂС‚ 10 С‚РѕРІР°СЂРѕРІ РёР· InSales СЃ РїСЂРѕРІРµСЂРєРѕР№ Marketplace С†РµРЅ. """ |
| **test_reimport_10_fixed.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅС‹Р№ С‚РµСЃС‚РѕРІС‹Р№ РїРµСЂРµРёРјРїРѕСЂС‚ 10 С‚РѕРІР°СЂРѕРІ РёР· InSales СЃ РїСЂРѕРІРµСЂРєРѕР№ Marketplace С†РµРЅ. РСЃРїСЂР°РІР»РµРЅРЅР°С... |
| **test_single_update.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **test_sync_api.py** | $escapedPath | Migration | """РўРµСЃС‚ Sync API РґР»СЏ СЃРІСЏР·Рё РїР°РїРєРё СЃ РєРѕРЅС„РёРіСѓСЂР°С†РёРµР№""" import json import sys |
| **test_tax_search.py** | $escapedPath | Migration | """РўРµСЃС‚ РїРѕРёСЃРєР° РЅР°Р»РѕРіРѕРІРѕР№ СЃС‚Р°РІРєРё Standard rate""" import json import sys |
| **test_verify_product_state.py** | $escapedPath | Migration | """ Unit-С‚РµСЃС‚ РґР»СЏ verify_product_state.py РџСЂРѕРІРµСЂСЏРµС‚ РєР°РЅРѕРЅРёС‡РµСЃРєСѓСЋ РјРѕРґРµР»СЊ Categories/Visibilities/Prices |
| **test_version_context.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **validate_batch_import.py** | $escapedPath | Migration | """ Р’Р°Р»РёРґР°С†РёСЏ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РїСЂРѕР±РЅРѕРіРѕ РёРјРїРѕСЂС‚Р° 10 С‚РѕРІР°СЂРѕРІ. Р—Р°РїСѓСЃРєР°РµС‚ verify_product_state.py РґР»СЏ РєР°Р¶РґРѕ... |
| **validate_category_navigation.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° РєР°С‚РµРіРѕСЂРёР№ Shopware РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ СЃС‚СЂСѓРєС‚СѓСЂС‹ InSales.""" from __future__ import annotat... |
| **validate_cover_pipeline.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **validate_properties_update.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **verify_500_imported.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅС‹С… 500 С‚РѕРІР°СЂРѕРІ.""" import sys |
| **verify_cover_associations_fix.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **verify_cover_fix.py** | $escapedPath | Migration | #!/usr/bin/env python3 """РџСЂРѕРІРµСЂРєР° РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚Рё СѓСЃС‚Р°РЅРѕРІРєРё coverId РїРѕСЃР»Рµ РёСЃРїСЂР°РІР»РµРЅРёСЏ.""" import sys |
| **verify_dimensions_weight_import.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РџСЂРѕРІРµСЂРєР° СЂР°Р·РјРµСЂРѕРІ Рё РІРµСЃР° РїРѕСЃР»Рµ РёРјРїРѕСЂС‚Р° С‚РѕРІР°СЂРѕРІ. |
| **verify_folder_config.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° РєРѕРЅС„РёРіСѓСЂР°С†РёРё РїР°РїРєРё Product Media""" import json import sys |
| **verify_full_import_results.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РџСЂРѕРІРµСЂРєР° СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РїРѕР»РЅРѕРіРѕ РёРјРїРѕСЂС‚Р° С‚РѕРІР°СЂР°: |
| **verify_import_results_detailed.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ Р”РµС‚Р°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РёРјРїРѕСЂС‚Р°: |
| **verify_last_import.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂРєР° РїРѕСЃР»РµРґРЅРµРіРѕ РёРјРїРѕСЂС‚Р° - РїРѕР»СѓС‡Р°РµРј С‚РѕРІР°СЂС‹ РЅР°РїСЂСЏРјСѓСЋ С‡РµСЂРµР· Search API """ |
| **verify_marketplace_final.py** | $escapedPath | Migration | """ Р¤РёРЅР°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° Marketplace С†РµРЅ РїРѕСЃР»Рµ РёРјРїРѕСЂС‚Р° """ |
| **verify_marketplace_price.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° Marketplace С†РµРЅС‹ Сѓ С‚РѕРІР°СЂР°""" import json from pathlib import Path |
| **verify_marketplace_prices.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂРєР° РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚Рё РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ Marketplace С†РµРЅ РІ Shopware 6. РџСЂРѕРІРµСЂСЏРµС‚: |
| **verify_media_thumbnails.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **verify_product_categories_after_sync.py** | $escapedPath | Migration | #!/usr/bin/env python3 """ РџСЂРѕРІРµСЂРєР° РєР°С‚РµРіРѕСЂРёР№ С‚РѕРІР°СЂР° РїРѕСЃР»Рµ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё Shopware. |
| **verify_product_number.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° productNumber РїРѕСЃР»Рµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ""" |
| **verify_product_state.py** | $escapedPath | Migration | """ РџСЂРѕРІРµСЂРєР° С„Р°РєС‚РёС‡РµСЃРєРѕРіРѕ СЃРѕСЃС‚РѕСЏРЅРёСЏ РёРјРїРѕСЂС‚РёСЂРѕРІР°РЅРЅРѕРіРѕ С‚РѕРІР°СЂР° РІ Shopware С‡РµСЂРµР· API. РўРѕР»СЊРєРѕ С‡С‚Р... |
| **verify_test_product.py** | $escapedPath | Migration | """РџСЂРѕРІРµСЂРєР° С‚РµСЃС‚РѕРІРѕРіРѕ С‚РѕРІР°СЂР° 500944170""" import json from pathlib import Path |
| **verify_thumbnails_after_fix.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """РџСЂРѕРІРµСЂРєР° thumbnails РїРѕСЃР»Рµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ""" |
| **verify_update_result.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **test_single_product_import.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **update_category_id_to_path.py** | $escapedPath | Migration | """ РћР±РЅРѕРІР»СЏРµС‚ category_id_to_path.json, РґРѕР±Р°РІР»СЏСЏ РЅРµРґРѕСЃС‚Р°СЋС‰РёРµ category_id РёР· CSV """ |
| **update_category_path_with_uuid.py** | $escapedPath | Migration | """ РћР±РЅРѕРІР»СЏРµС‚ category_id_to_path.json, РґРѕР±Р°РІР»СЏСЏ UUID РґР»СЏ category_id 23682913 """ |
| **update_override_template.py** | $escapedPath | Migration | #!/usr/bin/env python3 # -*- coding: utf-8 -*- """ |
| **verify_cleanup.py** | $escapedPath | Migration | """ Р’РµСЂРёС„РёРєР°С†РёСЏ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РѕС‡РёСЃС‚РєРё РґСѓР±Р»РёСЂРѕРІР°РЅРЅС‹С… СЃРІРѕР№СЃС‚РІ Рё С„РёР»СЊС‚СЂРѕРІ. РЎРєСЂРёРїС‚ РїСЂРѕРІРµСЂСЏРµС‚: |
| **inspect_columns.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.diagnostics.inspect_columns. """ |
| **inspect_columns_v2.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.archive.inspect_columns_v2. """ |
| **inspect_honeywell.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.diagnostics.inspect_honeywell. """ |
| **inventory_scripts.ps1** | $escapedPath | Utilities | <# .SYNOPSIS     Р“РµРЅРµСЂРёСЂСѓРµС‚ РєР°С‚Р°Р»РѕРі РІСЃРµС… СЃРєСЂРёРїС‚РѕРІ (.py, .ps1, .sh) РІ РїСЂРѕРµРєС‚Рµ. |
| **measure_rtt.ps1** | $escapedPath | Utilities | # РР·РјРµСЂРµРЅРёРµ RTT РґРѕ chatgpt.com $results = @() $count = 10 |
| **decrypt_credentials.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """Decrypt legacy n8n credentials exported from SQLite.""" from __future__ import annotations |
| **recreate_credentials.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """Recreate decrypted credentials in the new n8n instance via Public API.""" from __future__ import annotations |
| **restore_workflows.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """Import recovered workflows into the new n8n instance via Public API.""" from __future__ import annotations |
| **reset-n8n-password.sh** | $escapedPath | Utilities | #!/bin/bash # РЎРєСЂРёРїС‚ РґР»СЏ СЃР±СЂРѕСЃР° РїР°СЂРѕР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ n8n # РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: ./reset-n8n-password.sh |
| **reset-password-simple.sh** | $escapedPath | Utilities | #!/bin/bash # РџСЂРѕСЃС‚РѕР№ СЃРєСЂРёРїС‚ СЃР±СЂРѕСЃР° РїР°СЂРѕР»СЏ n8n DB="/root/.n8n/database.sqlite" |
| **setup_xray_vps.sh** | $escapedPath | Utilities | #!/bin/bash set -e echo "=== X-Ray Server Setup ===" |
| **check_and_start_xray.ps1** | $escapedPath | Diagnostics | # X-Ray Diagnostic and Startup Script # Checks X-Ray status and starts it if needed Set-StrictMode -Version Latest |
| **create_firefox_gpt_shortcut.ps1** | $escapedPath | Utilities | # Script to create a Firefox shortcut for ChatGPT via VPS USA proxy Set-StrictMode -Version Latest $ErrorActionPreference = 'Continue' |
| **create_vps_gpt_shortcut.ps1** | $escapedPath | Utilities | <# .SYNOPSIS     РЎРѕР·РґР°РµС‚ СЏСЂР»С‹Рє "VPS GPT" РЅР° СЂР°Р±РѕС‡РµРј СЃС‚РѕР»Рµ РґР»СЏ Chrome СЃ SOCKS5 proxy. |
| **__init__.py** | $escapedPath | Utilities | """ РњРѕРґСѓР»Рё РґРёР°РіРЅРѕСЃС‚РёРєРё РґР»СЏ ChatGPT USA Route. """ |
| **dns_leak.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ DNS leak РґРёР°РіРЅРѕСЃС‚РёРєР° С‡РµСЂРµР· nslookup. |
| **http_timing.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ HTTP timing РґРёР°РіРЅРѕСЃС‚РёРєР° С‡РµСЂРµР· curl -w. |
| **idle_tcp.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ Idle TCP stability С‚РµСЃС‚. |
| **playwright_har.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ Browser HAR collection С‡РµСЂРµР· Playwright (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ). |
| **tcp_rtt.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ TCP RTT РґРёР°РіРЅРѕСЃС‚РёРєР° С‡РµСЂРµР· curl timing. |
| **tls_handshake.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ TLS handshake РґРёР°РіРЅРѕСЃС‚РёРєР° С‡РµСЂРµР· openssl s_client. |
| **ws_echo.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ WebSocket stability С‚РµСЃС‚ С‡РµСЂРµР· РїСѓР±Р»РёС‡РЅС‹Р№ echo endpoint (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ). |
| **enable_chatgpt_usa.ps1** | $escapedPath | Utilities | <# .SYNOPSIS     Р’РєР»СЋС‡Р°РµС‚ ChatGPT USA Route: РїРѕРґРіРѕС‚Р°РІР»РёРІР°РµС‚ РєРѕРЅС„РёРіРё X-Ray Рё СЃРѕР·РґР°РµС‚ СЏСЂР»С‹Рє Р±СЂР°СѓР·РµСЂР°. |
| **fix_chatgpt_proxy.ps1** | $escapedPath | Maintenance | # Fix ChatGPT Proxy Issues # Comprehensive diagnostic and fix script Set-StrictMode -Version Latest |
| **rollback_chatgpt_usa.ps1** | $escapedPath | Utilities | <# .SYNOPSIS     РћС‚РєР°С‚С‹РІР°РµС‚ ChatGPT USA Route: РІРѕСЃСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ backup РєРѕРЅС„РёРіРѕРІ Рё РѕСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ X-Ray (РµСЃР»Рё... |
| **run_all.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ Р“Р»Р°РІРЅС‹Р№ runner РґРёР°РіРЅРѕСЃС‚РёРєРё ChatGPT USA Route. |
| **setup_autostart_task.ps1** | $escapedPath | Utilities | # Script to setup Xray Autostart via Windows Task Scheduler $taskName = "XrayChatGPTProxy" $scriptPath = "C:\cursor_project\biretos-automation\net_diag_chatg... |
| **setup_xray_server_vps.ps1** | $escapedPath | Utilities | # Setup X-Ray Server on VPS # Automatically configures and starts X-Ray server on VPS Set-StrictMode -Version Latest |
| **test_proxy_detailed.ps1** | $escapedPath | Diagnostics | # Detailed Proxy Test Script # Tests if proxy actually works for chatgpt.com Set-StrictMode -Version Latest |
| **test_xray_connection.ps1** | $escapedPath | Diagnostics | # X-Ray Connection Test Script # Tests X-Ray proxy connection to ChatGPT through VPS Set-StrictMode -Version Latest |
| **xray_render.py** | $escapedPath | Utilities | #!/usr/bin/env python3 """ РЈС‚РёР»РёС‚Р° РґР»СЏ РіРµРЅРµСЂР°С†РёРё X-Ray РєРѕРЅС„РёРіРѕРІ РёР· С€Р°Р±Р»РѕРЅРѕРІ СЃ РїРѕРґСЃС‚Р°РЅРѕРІРєРѕР№ РїРµСЂРµРјРµРЅРЅ... |
| **enrich_zapi_excel.py** | $escapedPath | Data Enrichment | from __future__ import annotations import argparse import asyncio |
| **find_reliable_photo.py** | $escapedPath | Data Enrichment | from __future__ import annotations import argparse import asyncio |
| **generate_brand_excel.py** | $escapedPath | Data Enrichment | """ РРЅС‚РµСЂР°РєС‚РёРІРЅС‹Р№ СЃРєСЂРёРїС‚ РґР»СЏ РіРµРЅРµСЂР°С†РёРё Excel СЃ С‚РѕРІР°СЂР°РјРё Р±СЂРµРЅРґР° С‡РµСЂРµР· Perplexity. """ |
| **lookup.py** | $escapedPath | Data Enrichment | """ CLI-СЃРєСЂРёРїС‚ РґР»СЏ Р·Р°РїСѓСЃРєР° Perplexity product lookup. """ |
| **__init__.py** | $escapedPath | Data Enrichment | """РџР°РєРµС‚ РґР»СЏ РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ Perplexity product lookup.""" |
| **brand_sampler.py** | $escapedPath | Data Enrichment | """ РЎР±РѕСЂС‰РёРє РїСЂРёРјРµСЂРѕРІ С‚РѕРІР°СЂРѕРІ РґР»СЏ СѓРєР°Р·Р°РЅРЅРѕРіРѕ Р±СЂРµРЅРґР° С‡РµСЂРµР· Perplexity (OpenRouter). """ |
| **excel_writer.py** | $escapedPath | Data Enrichment | # reserved for future Excel enrichment from __future__ import annotations from typing import Any, Awaitable, Callable, Dict, List, Optional |
| **page_screenshot.py** | $escapedPath | Data Enrichment | from __future__ import annotations import os from pathlib import Path |
| **perplexity_client.py** | $escapedPath | Data Enrichment | """ РљР»РёРµРЅС‚ РґР»СЏ РѕР±СЂР°С‰РµРЅРёСЏ Рє Perplexity С‡РµСЂРµР· OpenRouter. Р“Р°СЂР°РЅС‚РёСЂСѓРµС‚, С‡С‚Рѕ РјРµС‚РѕРґ lookup РЅРёРєРѕРіРґР° РЅРµ РІС‹Р±СЂ... |
| **product_lookup.py** | $escapedPath | Data Enrichment | """ Р’С‹СЃРѕРєРѕСѓСЂРѕРІРЅРµРІР°СЏ РѕР±РµСЂС‚РєР° РІРѕРєСЂСѓРі PerplexityClient РґР»СЏ РїРѕР»СѓС‡РµРЅРёСЏ РґР°РЅРЅС‹С… Рѕ РїСЂРѕРґСѓРєС‚Рµ. """ |
| **reliable_photo_finder.py** | $escapedPath | Data Enrichment | from __future__ import annotations import re from typing import Iterable, List, Optional, Tuple |
| **screenshot_uploader.py** | $escapedPath | Data Enrichment | from __future__ import annotations import mimetypes import os |
| **recalc_rubles.py** | $escapedPath | Utilities | """ Compatibility shim for scripts.analytics.recalc_rubles. """ |
| **run_cursorvpn.ps1** | $escapedPath | Utilities | [CmdletBinding()] param() Set-StrictMode -Version Latest |
| **__init__.py** | $escapedPath | Utilities | """Namespace package for organized scripts.""" |
| **__init__.py** | $escapedPath | Utilities | """Analytics scripts package.""" |
| **analyze_categories_deep.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **analyze_extended_core.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **analyze_honeywell_core.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **analyze_remaining_lots.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **analyze_top_50_deep.py** | $escapedPath | Analytics | import pandas as pd import os import re |
| **compare_cores.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **deep_analyze_14_16.py** | $escapedPath | Utilities | import pandas as pd import glob import os |
| **extract_honeywell_core.py** | $escapedPath | Utilities | import pandas as pd import re # РќР°СЃС‚СЂРѕР№РєРё |
| **find_global_top5.py** | $escapedPath | Utilities | import pandas as pd import glob import os |
| **recalc_rubles.py** | $escapedPath | Utilities | import pandas as pd import glob import os |
| **__init__.py** | $escapedPath | Utilities | """Archive for legacy scripts.""" |
| **compare_cores_v3.py** | $escapedPath | Analytics | import pandas as pd import glob import os |
| **extract_honeywell_core_v2.py** | $escapedPath | Utilities | import pandas as pd import re import sys |
| **inspect_columns_v2.py** | $escapedPath | Utilities | import pandas as pd import glob import os |
| **__init__.py** | $escapedPath | Utilities | """Diagnostics scripts package.""" |
| **check_my_top5.py** | $escapedPath | Diagnostics | import pandas as pd import glob import os |
| **inspect_columns.py** | $escapedPath | Utilities | import pandas as pd try:     df = pd.read_excel("downloads/РҐР°РЅРёРІРµР»Р»_enriched.xlsx") |
| **inspect_honeywell.py** | $escapedPath | Utilities | import pandas as pd import os import re |
| **__init__.py** | $escapedPath | Utilities | """Maintenance scripts package.""" |
| **__init__.py** | $escapedPath | Utilities | """Utility scripts package.""" |
| **canon_registry.py** | $escapedPath | Utilities | from __future__ import annotations import logging from datetime import datetime, timezone |
| **__init__.py** | $escapedPath | Utilities | from __future__ import annotations from dataclasses import dataclass, field from enum import Enum |
| **categories.py** | $escapedPath | Utilities | from __future__ import annotations from typing import Any, Dict, List, Optional from clients import ShopwareClient |
| **manufacturer.py** | $escapedPath | Utilities | from __future__ import annotations from typing import Any, Dict, Optional from canon_registry import CanonRegistry |
| **media.py** | $escapedPath | Utilities | from __future__ import annotations import io import os |
| **prices.py** | $escapedPath | Utilities | from __future__ import annotations from typing import Any, Dict from canon_registry import CanonRegistry |
| **skeleton.py** | $escapedPath | Utilities | from __future__ import annotations import uuid from typing import Any, Dict |
| **verify.py** | $escapedPath | Utilities | from __future__ import annotations import subprocess import sys |
| **visibilities.py** | $escapedPath | Utilities | from __future__ import annotations from typing import Any, Dict from clients import ShopwareClient |
| **normalize_entities.py** | $escapedPath | Utilities | from __future__ import annotations import argparse import json |
| **pipeline_import.py** | $escapedPath | Utilities | from __future__ import annotations import argparse import json |
| **__init__.py** | $escapedPath | Utilities | """ T-Bank Webhook Gateway Lightweight receiver РґР»СЏ РїСЂРёС‘РјР° webhook РѕС‚ Рў-Р‘Р°РЅРєР° Рё РїСЂРѕРєСЃРёСЂРѕРІР°РЅРёСЏ РІ n8n |
| **forwarder.py** | $escapedPath | Utilities | """ HTTP forwarder РґР»СЏ РїСЂРѕРєСЃРёСЂРѕРІР°РЅРёСЏ webhook РІ n8n """ |
| **logger.py** | $escapedPath | Utilities | """ Structured logging РґР»СЏ webhook gateway """ |
| **main.py** | $escapedPath | Utilities | """ FastAPI РїСЂРёР»РѕР¶РµРЅРёРµ РґР»СЏ РїСЂРёС‘РјР° webhook РѕС‚ Рў-Р‘Р°РЅРєР° """ |
| **validators.py** | $escapedPath | Utilities | """ Р’Р°Р»РёРґР°С†РёСЏ payload РѕС‚ Рў-Р‘Р°РЅРєР° webhook """ |
| **tmp_tbank_curl.sh** | $escapedPath | Utilities | #!/bin/bash set -euo pipefail set -a |
