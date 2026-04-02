Place surveillance demo videos in this directory using the pattern:

- `nv1.mp4`
- `nv2.mp4`
- `nv3.mp4`

The Python backend discovers `nv*.mp4` files here and exposes them as surveillance
feeds in the dashboard. The feed count in the frontend is based on how many files
exist in this folder.

Per-feed mode and display name can be managed from the frontend route:

- `/admin`
