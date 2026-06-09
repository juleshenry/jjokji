# jjokji

Small CLI repo that orchestrates sibling language-note repos.

Expected layout:

```text
minhasnotas/
  jjokji/
  french_notes/
  portuguese_notes/
  korean_notes/
  castellano_notes/
  all_lang_notes/
```

Commands:

```bash
./jj doctor
./jj bootstrap
./jj add pt en "convite" "invitation"
./jj pt en "convite" "invitation"
```

`jj` writes to the target language repo and to `all_lang_notes`, then runs `brainbrew`.
