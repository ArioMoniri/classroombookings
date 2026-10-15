def lum(h):
    h = h.lstrip("#"); r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def cr(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)
light_bg = {"white": "#FFFFFF", "scene-lo #eef0f4": "#EEF0F4", "chrome-light #f7f8fa": "#F7F8FA", "regular-glass #fafbfc": "#FAFBFC", "ultra-thin #f3f4f7": "#F3F4F7", "gh-header #F4F6F9": "#F4F6F9"}
dark_bg = {"scene #0d0e12": "#0D0E12", "chrome-dark #1b1c21": "#1B1C21", "thick-dark #222328": "#222328", "gh-dark #0d1117": "#0D1117", "gh-header #11161D": "#11161D"}
for name, fg in {"blue #0A63D1": "#0A63D1", "navy #0B3F86": "#0B3F86", "ink #1D1D1F": "#1D1D1F", "tile #0A63D1": "#0A63D1"}.items():
    print(name.ljust(16), "  ".join(f"{k.split()[0]} {cr(fg, v):5.2f}" for k, v in light_bg.items()))
for name, fg in {"blue-dk #4DA0FF": "#4DA0FF", "sky #A9D0FF": "#A9D0FF", "ink-dk #F5F5F7": "#F5F5F7", "tile #0A63D1": "#0A63D1"}.items():
    print(name.ljust(16), "  ".join(f"{k.split()[0]} {cr(fg, v):5.2f}" for k, v in dark_bg.items()))
print("white on tile", round(cr("#FFFFFF", "#0A63D1"), 2), "| blue vs navy (piece separation)", round(cr("#0A63D1", "#0B3F86"), 2), "| blue-dk vs sky", round(cr("#4DA0FF", "#A9D0FF"), 2))
print("mono black on white", round(cr("#000000", "#FFFFFF"), 2), "| mono white on gh-dark", round(cr("#FFFFFF", "#0D1117"), 2))
