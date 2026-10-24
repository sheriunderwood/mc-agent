# Shopping inbox

Stores the avatar has heard about and noted with `note_store`.
`tools/shop_lookup.py inbox` looks each one up on the Marketplace, finds its
in-world SLURL, checks the region still exists, and files it under
`shopping/<category>.md`. You can add lines here by hand, in the same format.

Format: `- [ ] Store name | category | where we heard about it`
Categories: clothing, skins, hair, shoes, jewelry, animations, gestures,
tattoos-makeup, accessories, other

