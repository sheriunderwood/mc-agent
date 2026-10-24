# Friends

People the avatar knows and has talked with. This is an index: everything
known about a person is in `friends/<account name>/`, one or more `.md` files
of facts.

The agent adds people here as it gets to know them (`remember_friend`), keeps
Pronouns and Contact current (`set_friend_info`), and looks people up by
**UUID** (`recall_friend`). You can add people by hand too, in the same format
(yourself, for a start).

- **Pronouns**: how to refer to them. `?` means not known yet: use their name
  or they/them, and never guess.
- **Contact**:
  - `ok`: the avatar may start conversations.
  - `quiet`: they haven't been replying, so the avatar only answers when they write first.
  - `do-not-contact`: they asked to be left alone. The avatar only answers when
    they write first, and never asks them anything.

| UUID | Account name | Display name | Pronouns | Contact | First met | Folder |
|------|--------------|--------------|----------|---------|-----------|--------|
