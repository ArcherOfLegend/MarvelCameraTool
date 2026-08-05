# Marvel 3 Camera Tool

Edits UMvC3 `.lmcm` camera files.

## Download

Grab `Marvel3CameraTool.exe` from [Releases](../../releases) and run it.

## Running from source
```
pip install PySide6
python m3c_gui.py
```

## Using it

Open a `.lmcm`, or drag one onto the window. You'll get every camera in the list and their name by approximation.

| Button | What it does |
| --- | --- |
| Extract selected | saves the highlighted camera as a `.m3c` |
| Extract all | saves every camera into a folder you pick |
| Inject camera | puts a `.m3c` into a slot you choose |
| Remove selected | deletes a camera |

You can also drag a `.m3c` onto the window to inject it.

The title bar shows a star while there are unsaved changes. Files will not update till you save.

## The preview

I coded this in a delirious hay fever nightmare and have no idea how it works.

## Slot numbers

The slot number decides which move a camera belongs to.

| Slot | Usually |
| --- | --- |
| 0 to 4 | hypers |
| 10 to 13 | team hyper combos |
| 20 | win pose |
| 50 | cinematic |
| 100 | cinematic, only Galactus so far |

These labels are worked out from the game files rather than documented. Sometimes the cinematic is Cam 12

## When something goes wrong

I dunno. What you see is what you get. Blender is the most accurate representation of how the camera wil llook.

## Building the exe yourself
```
pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean m3c_gui.spec
```

PyInstaller does not cross compile. If you wanna run this on linux you will have to build it yourself.

If a build will not start and you cannot see why, change `console=False` to
`console=True` in `m3c_gui.spec` and rebuild. You will get a terminal window
with the error in it.

## Files

| File | What it is |
| --- | --- |
| `m3c_gui.py` | the window |
| `m3c_preview.py` | the preview pictures |
| `m3c.py` | reads and writes the camera files |
| `m3c_gui.spec` | settings for the exe build |
| `requirements-build.txt` | the exact versions the build uses |
| `.github/workflows/build.yml` | the automatic build |
