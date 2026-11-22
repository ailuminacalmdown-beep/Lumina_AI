#!/usr/bin/env python3
import shutil

# Sauvegarde
shutil.copy("lumina_server.py", "lumina_server.py.bak")
print("Sauvegarde : lumina_server.py.bak")

with open("lumina_server.py", "r") as f:
    content = f.read()

# 1. Ajouter VISION_MODELS après VALID_MODELS
if "VISION_MODELS" not in content:
    content = content.replace(
        "VALID_MODELS = set(MODELS_DISPLAY.keys())\n",
        "VALID_MODELS = set(MODELS_DISPLAY.keys())\n\n# Modèles supportant le format multimodal (vision) sur Groq.\nVISION_MODELS = {\n    PRIME_MODEL,\n}\n"
    )

# 2. Ajouter is_multimodal avant call_groq
if "def is_multimodal" not in content:
    content = content.replace(
        "\ndef call_groq(\n",
        "\ndef is_multimodal(messages):\n    \"\"\"Détecte si le payload contient une image (format OpenAI multimodal).\"\"\"\n    for msg in messages:\n        content = msg.get(\"content\")\n        if isinstance(content, list):\n            for item in content:\n                if isinstance(item, dict) and item.get(\"type\") == \"image_url\":\n                    return True\n    return False\n\n\ndef call_groq(\n"
    )

# 3. Modifier la construction de models_to_try dans call_groq
old_block = '''    models_to_try = [
        preferred_model
    ]

    for model in GROQ_MODELS_CASCADE:

        if model not in models_to_try:
            models_to_try.append(model)'''

new_block = '''    is_mm = is_multimodal(messages)

    models_to_try = [
        preferred_model
    ]

    for model in GROQ_MODELS_CASCADE:

        if model not in models_to_try:

            if is_mm and model not in VISION_MODELS:
                print(
                    f"[GROQ] Skip {model} — "
                    f"non-vision, multimodal payload"
                )
                continue

            models_to_try.append(model)'''

content = content.replace(old_block, new_block)

# 4. Ajouter gestion 413 avant le bloc 400/404
old_400 = '''                    elif r.status_code in (
                        400,
                        404
                    ):'''

new_400 = '''                    elif r.status_code == 413:

                        print(
                            f"[GROQ] 413 Payload Too Large "
                            f"{model}"
                        )

                        # Image trop lourde pour Groq (limite base64 ~4MB).
                        # Ne pas cascader : le problème est la taille, pas le modèle.
                        if is_mm:
                            break

                        time.sleep(1)

                    elif r.status_code in (
                        400,
                        404
                    ):'''

content = content.replace(old_400, new_400)

# 5. Forcer PRIME_MODEL quand has_image dans chat()
old_web = '''    # Une recherche web doit utiliser Prime.
    if use_web and intent.get("web"):

        model_req = PRIME_MODEL
        route_reason = "web"'''

new_web = '''    # Une image doit impérativement utiliser Prime (seul modèle vision).
    if has_image:
        model_req = PRIME_MODEL
        route_reason = "vision"
        img_len = len(image_data) if image_data else 0
        print(
            f"[VISION] Image reçue, taille base64: {img_len} chars "
            f"(~{img_len * 3 // 4} bytes)"
        )

    # Une recherche web doit utiliser Prime.
    if use_web and intent.get("web"):

        model_req = PRIME_MODEL
        route_reason = "web"'''

content = content.replace(old_web, new_web)

with open("lumina_server.py", "w") as f:
    f.write(content)

print("✅ Patch vision appliqué.")
