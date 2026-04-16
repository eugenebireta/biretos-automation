import shutil
import sys
path = "/etc/nginx/conf.d/shopware.conf"
shutil.copy(path, path + ".bak.biretos")
with open(path) as f:
    txt = f.read()
block = '\n    # biretos-catalog-photos-location\n    location ^~ /catalog/ {\n        alias /var/www/catalog/;\n        expires 30d;\n        add_header Cache-Control "public, immutable";\n        access_log off;\n    }\n'
insert_before = "    location / {"
idx = txt.rfind(insert_before)
if idx == -1:
    print("ERROR: could not find insertion point"); sys.exit(1)
txt = txt[:idx] + block + txt[idx:]
with open(path, "w") as f:
    f.write(txt)
print("Patched OK")
