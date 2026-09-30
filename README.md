# jjokji

Language notes monorepo plus the `jj` CLI that turns them into an Anki deck.

Layout:

```text
jjokji/
  jj
  all_lang_notes/   # brainbrew source + Anki build
  notes/
    french/
    korean/
    portuguese/
    spanish/
```

Commands:

```bash
./jj doctor
./jj add pt en "convite" "invitation"
./jj pt en "convite" "invitation"
```

`jj` writes to `notes/<lang>/` and to `all_lang_notes`, then runs `brainbrew`.
