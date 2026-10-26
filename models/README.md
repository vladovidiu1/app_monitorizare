# Model local (nu se versionează în Git)

Pregătire explicită de către dezvoltator: `python scripts/download_model.py` din rădăcina repository-ului.
Este descărcat numai `Qwen3-8B-Q4_K_M.gguf`, la revizia și SHA256 din manifestul versionat
`src/focusdesk/resources/ai-model.json`. Nu modifica hash-ul pentru a accepta un fișier corupt.

În distribuție, acest folder stă lângă FocusDesk.exe, în afara workspace-ului și a directorului temporar onefile.
Licența și atribuirea Qwen sunt incluse în `licenses/`. Detalii: [docs/AI.md](../docs/AI.md).
