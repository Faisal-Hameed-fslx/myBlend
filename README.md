# myBlend Recovery

`myBlend Recovery` is a Blender add-on for managing compact, external recovery
versions of complete `.blend` scenes. It keeps the working `.blend` file unchanged
and stores compressed snapshots in one hidden history folder beside it.

## Features

- Named, compressed full-scene checkpoints
- Restore complete Blender scenes without creating a new version
- Optional backup of external image files used by the scene
- Restore image paths to the exact image stored with the selected version
- Version number and image count display
- Maximum version-count retention
- Maximum total-history-size retention
- Delete individual versions and their image backups
- Atomic snapshot writing through temporary files

## Install

1. In Blender, open **Edit > Preferences > Add-ons**.
2. Click **Install...**.
3. Select `myBlend.zip`.
4. Enable **myBlend Recovery**.
5. Save the current `.blend` file before creating the first checkpoint.

## Usage

Open the 3D Viewport and press **N**. Select the **myBlend** tab.

### Save a version

1. Enter a name in **Version Name**, such as `Original`, `Before Rig`, or `Final`.
2. Enable **Include External Images** if the scene uses image files.
3. Click **Save myBlend Version**.

### Restore a version

1. Select a version in **Saved Version**.
2. Click **Restore Selected Version**.

Restore does not create another history entry. To create a new checkpoint after
editing the restored scene, enter a new name and explicitly click **Save myBlend
Version**.

### Manage storage

- **Keep Versions** limits the number of retained checkpoints.
- **Max History Size (MB)** limits the combined compressed snapshot and image size.
- **Apply Retention Limit** removes the oldest versions until both limits are met.
- **Delete Selected Version** removes the selected snapshot and its copied images.

## Storage layout

For a scene at `D:\Projects\Character.blend`:

```text
D:\Projects\Character.blend
D:\Projects\.myBlend.history\
  manifest.json
  myBlend_20261027_104500_Original.blend.gz
  assets\
    myBlend_20261027_104500_Original\
      reference.png
```

The history directory is hidden on Windows. `manifest.json` stores version names,
timestamps, sizes, image counts, and the original image paths.

## Important limitations

- Snapshots preserve the complete `.blend` file, but external non-image assets
  such as caches, linked libraries, HDRIs, and geometry-node assets may still
  require their original files.
- Packed Blender data is included in the `.blend` snapshot.
- Restoring replaces the current scene. Save a new checkpoint first if the
  current unsaved work matters.
- History is stored beside the project. Copy the `.myBlend.history` folder with
  the `.blend` file for off-device backup.
- Snapshots created by newer Blender versions may not open in older versions.

## License

Personal-use project. Add a license file before redistributing this add-on.
