# HawaiMama Technical System Report

## 1. Document Purpose

This report is written for technical reviewers, engineering leads, and government-side technical administrators who need a clear description of what the HawaiMama system currently does, how its components are arranged, what is live versus simulated, and what limitations remain in the current implementation.

This document condenses:

- the implemented frontend and backend behavior
- the AI pipeline flow
- the storage and database model
- the surveillance management workflow
- the mock integration layers used for demonstration
- the current known limitations and pending work

## 2. System Summary

HawaiMama is currently structured as:

- `Next.js` frontend for operator UI
- `FastAPI` backend for API, media serving, and admin actions
- `Python` computer vision pipeline for traffic monitoring and violation generation
- `PostgreSQL` for persistent operational records
- `Local object storage or S3` for media evidence

At a high level, the system does the following:

1. discovers surveillance sources from the backend surveillance directory
2. streams raw and processed surveillance media to the frontend
3. detects vehicles and selected traffic violations
4. enriches detected plates with mock DoTM-style owner data
5. saves evidence screenshots and short clips
6. persists violations in PostgreSQL
7. generates challans after violation verification

## 3. Audience Split

There are two documentation audiences:

- non-technical operators
- technical administrators and maintainers

The operator-facing guide is stored at:

- [`admin_manual/admin_panel_manual.md`](/home/sameep/Documents/Code/projects/HawaiMama/docs/admin_manual/admin_panel_manual.md)

This technical report is for the second audience.

## 4. Technology Stack

### 4.1 Frontend

- Next.js 16
- React
- TypeScript
- Zod
- custom dashboard styling in `admin/app/globals.css`

### 4.2 Backend

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic
- python-dotenv
- python-multipart

### 4.3 Computer Vision and Detection

- Ultralytics YOLO
- OpenCV
- EasyOCR
- NumPy
- lap

### 4.4 Database and Storage

- PostgreSQL
- psycopg
- local storage under `core/wwwroots`
- optional S3-compatible object storage via boto3

### 4.5 Media Tooling

- FFmpeg for short evidence clip generation

## 5. Repository Areas That Matter

### 5.1 Frontend

- `admin/app/`
- `admin/components/`
- `admin/lib/api.ts`
- `admin/types/`

### 5.2 Backend

- `core/src/traffic_monitoring/server/app.py`
- `core/src/traffic_monitoring/server/repository.py`
- `core/src/traffic_monitoring/pipeline/runtime.py`
- `core/src/traffic_monitoring/tracking.py`
- `core/src/traffic_monitoring/annotations.py`
- `core/src/traffic_monitoring/storage.py`
- `core/src/traffic_monitoring/mock_dotm_service.py`

### 5.3 Data and Media

- `core/surveillance/`
- `core/surveillance/output/`
- `core/input/`
- `core/output/`
- `core/wwwroots/`
- `core/data/mock_vehicle_registry.json`

### 5.4 Project Docs

- `docs/last_minute.md`

## 6. Current Architecture

### 6.1 Frontend Role

The frontend is now a UI layer only.

It does not own the operational backend logic.

Its responsibilities are:

- render live surveillance cards
- call FastAPI endpoints
- show violations, accidents, and challans
- let admins manage surveillance feeds
- display saved evidence and challan details

### 6.2 Backend Role

The FastAPI backend is the system coordinator for:

- surveillance feed discovery
- processed stream serving
- raw media serving
- admin feed creation and removal
- violation persistence
- challan generation
- event serving
- camera configuration persistence

### 6.3 Pipeline Role

The traffic monitoring pipeline handles:

- detection and tracking
- OCR and plate recognition
- rider and helmet analysis
- wrong lane and overspeed logic
- annotated output generation
- event detection hooks for the FastAPI layer

## 7. Surveillance Model

### 7.1 Source of Truth

The surveillance registry is derived from files in:

- `core/surveillance/`

Feeds are discovered by scanning files named like:

- `nv1.mp4`
- `nv2.mov`
- `nv3.webm`

Supported extensions currently include:

- `.mp4`
- `.mov`
- `.m4v`
- `.webm`
- `.avi`
- `.mkv`

### 7.2 Feed Discovery

The backend discovers feeds in `server/app.py` by:

- scanning `core/surveillance/`
- sorting by `nv` suffix
- creating camera entries such as `nv1`, `nv2`, and so on

Each discovered camera is represented with:

- `id`
- `source`
- `location`
- `location_link`
- `status`
- `system_mode`

### 7.3 Raw vs Processed Surveillance

The live dashboard supports two viewing modes:

#### Raw mode

- shows raw surveillance files from `/surveillance-media/...`
- is the default mode
- avoids heavy processing on all visible feeds

#### System output mode

- grid cards use processed preview clips from `/surveillance-output/...` when available
- opening one feed uses the live processed stream from `/camera/{id}/stream`
- reduces compute cost by only doing full live processing for the selected feed

### 7.4 Feed Management

The admin panel allows:

- changing feed location text
- changing feed system mode
- uploading a new video file as a new surveillance source
- removing an existing surveillance source

When a new source is added:

1. frontend uploads the selected video file
2. backend assigns the next ID such as `nv10`
3. backend copies the file into `core/surveillance/`
4. backend stores location and mode in PostgreSQL
5. the feed becomes available in both admin and live surveillance views

When a source is removed:

1. the surveillance file is deleted
2. any matching processed preview is deleted
3. output artifacts for that camera are deleted
4. the registry refreshes

This is intentionally file-based for the hackathon version.

## 8. API Surface

The backend currently exposes these functional groups.

### 8.1 Surveillance and Cameras

- `GET /surveillance/feeds`
- `GET /cameras`
- `GET /admin/cameras`
- `PATCH /admin/cameras/{camera_id}`
- `POST /admin/cameras`
- `DELETE /admin/cameras/{camera_id}`
- `GET /camera/{camera_id}/stream`
- `GET /video_feed`

### 8.2 Events and Logs

- `GET /events`
- `GET /violations`
- `GET /violations/{violation_id}`
- `POST /violations/{violation_id}/verify`
- `GET /accidents`
- `GET /accidents/{accident_id}`
- `POST /accidents/{accident_id}/verify`
- `GET /challans`
- `GET /challans/{challan_id}`

### 8.3 Traffic State

- `GET /traffic/state`
- `GET /traffic/lanes`

### 8.4 Mock Vehicle Lookup

- `GET /vehicle/{plate}`

### 8.5 Static Media

- `/surveillance-media`
- `/surveillance-output`
- `/inputs`
- `/snapshots`
- `/wwwroots`

## 9. Database Model

The PostgreSQL-backed admin repository currently maintains these logical record types:

- `cameras`
- `violations`
- `accidents`
- `challans`

### 9.1 Cameras

The `cameras` table stores:

- camera ID
- location
- status
- system mode
- source path
- metadata JSON

### 9.2 Violations

Violation records are stored with:

- event timestamp
- verification state
- source event key
- payload JSON

The JSON payload includes:

- camera ID
- violation code
- owner information
- plate number
- evidence URLs
- location
- mock-data flag

### 9.3 Challans

Challans are generated when a violation is verified.

They are stored with:

- challan ID
- linked violation ID
- payload JSON

### 9.4 Accidents

The structure exists, but the accident pipeline is not yet fully live in the same way as violations.

## 10. Evidence Storage Design

### 10.1 Purpose

When a violation is detected, the backend now attempts to store:

- a cropped vehicle screenshot
- a short clip around the event

### 10.2 Storage Backends

The storage abstraction supports:

- local object-storage-style saving
- S3-compatible object storage

The switch is controlled by:

- `USE_S3`

Configuration is documented in:

- `core/.env.example`

### 10.3 Local Storage Mode

When `USE_S3=false`:

- files are saved under `core/wwwroots/`
- the backend serves them under `/wwwroots/...`

### 10.4 S3 Mode

When `USE_S3=true`:

- evidence is uploaded through boto3
- URLs are built from bucket and S3 settings

### 10.5 Evidence Layout

Evidence keys are organized by:

- date
- camera ID
- camera location slug
- violation code
- track ID

This keeps evidence grouped by source and event type.

### 10.6 Snapshot Metadata

For each stored snapshot, the backend also stores a JSON metadata file with:

- plate
- owner
- address
- violation
- camera ID
- camera location
- timestamp
- image URL
- mock-data flag

## 11. Detection and Enrichment Flow

### 11.1 Pipeline Sequence

At runtime, the main processing path is:

1. open the video source
2. detect objects
3. track them frame to frame
4. perform OCR and plate recognition
5. enrich tracks with mock vehicle owner data
6. evaluate violations
7. annotate frames
8. record new events

### 11.2 Plate Recognition

Plate OCR is handled in `tracking.py`.

When a stable plate is read:

- the plate text is normalized
- mock DoTM lookup is performed through the local service layer
- track metadata is enriched with owner information

The pipeline does not depend on a remote HTTP call to do this.

That is intentional.

Both the API route and the pipeline use the same service object directly.

### 11.3 Owner Enrichment

Track metadata may include:

- `owner_name`
- `owner_address`
- `owner_vehicle_type`
- `vehicle_color`
- `registration_date`
- `owner_contact_number`
- `is_mock_data`

### 11.4 Overlay Enrichment

When owner information is available, the annotated overlay shows:

- plate
- violations
- owner name

This makes the demo feel closer to a government-use review workflow.

## 12. Mock DoTM Integration Layer

### 12.1 Why It Exists

Nepal vehicle ownership data is not available for direct real-world use in this project.

To simulate a realistic system architecture, HawaiMama uses a mock DoTM layer.

### 12.2 How It Works

The mock integration is implemented in:

- `core/src/traffic_monitoring/mock_dotm_service.py`

It provides:

- plate normalization
- record lookup
- deterministic demo fallback owner selection
- API response generation

### 12.3 Registry Data

The backing registry file is:

- `core/data/mock_vehicle_registry.json`

It contains realistic sample Nepali names, locations, vehicle types, colors, and registration dates.

### 12.4 API Behavior

`GET /vehicle/{plate}` returns:

- full vehicle details if found
- `not found` plus `is_mock_data: true` if not found

### 12.5 Pipeline Behavior

The pipeline itself uses the service layer directly instead of calling `/vehicle/{plate}` over HTTP.

This was chosen because it is:

- faster
- simpler
- less fragile
- closer to a real internal service integration

## 13. Violation and Challan Flow

### 13.1 Violation Creation

When the system sees a new violation:

1. it de-duplicates by camera, time, track, and violation code
2. it saves a snapshot
3. it tries to save a short clip
4. it builds a violation payload
5. it stores the payload in PostgreSQL
6. it adds an event entry for `/events`

### 13.2 What a Violation Payload Contains

The current frontend-facing violation payload includes:

- camera information
- owner information
- location
- plate number
- description
- screenshot URLs
- evidence clip URL
- source clip URL
- evidence provider
- mock-data flag

### 13.3 Verification

When the operator clicks:

- `Verify & Generate Challan`

the backend:

1. marks the violation as verified
2. creates a challan if one does not exist
3. links the challan to the violation

### 13.4 Challan Contents

Generated challans include:

- authority information
- owner details
- vehicle details
- offense details
- location
- officer block
- evidence references
- metadata including mock-data flag

## 14. Frontend Workflows

### 14.1 Live Dashboard

The live dashboard provides:

- search
- raw/system toggle
- feed detail view
- links into feed administration

### 14.2 Violation Review

The violation detail panel shows:

- owner name
- plate
- camera and location
- owner address
- vehicle color
- registration date
- evidence screenshots
- evidence video
- source clip link
- mock-data disclaimer when applicable

### 14.3 Challan Review

The challan detail panel shows:

- printable challan view
- owner and vehicle details
- offense details
- fine amount
- mock-data disclaimer

### 14.4 Feed Administration

The admin panel supports:

- feed search
- mode filtering
- location editing
- mode editing
- feed upload
- feed deletion

## 15. Operational Notes

### 15.1 Why Raw Mode Is the Default

Raw mode is the default because rendering processed streams for all visible cards is expensive.

The current design saves compute by:

- showing raw video in the grid by default
- only using the live processed stream when a single feed is opened in detail view with system output enabled

### 15.2 Why Upload Is Used for New Feeds

The hackathon feed-addition flow uses file upload instead of a raw filesystem path because:

- browser clients cannot safely provide trusted local server paths
- upload is the normal browser-safe pattern
- it keeps the backend in control of what becomes part of the surveillance registry

### 15.3 Why TestClient Smoke Test Was Not Run

An API-level upload/delete smoke test was not completed because the local FastAPI test client requires `httpx`, which is not installed in the backend environment.

Build, lint, and import-time validation were completed.

## 16. Known Simulations and Non-Production Areas

The following are currently simulated or hackathon-scoped:

- vehicle owner data via mock DoTM registry
- uploaded video files instead of direct CCTV hardware/RTSP integration
- some challan business data
- accident functionality depending on deployment state

## 17. Pending Work From Existing Docs

The current `docs/last_minute.md` file records two pending items:

- update challan/fine policy values for `plate_missing`
- update challan/fine policy values for `plate_unreadable`

These are policy-completion items, not just UI issues.

## 18. Current Strengths

What is already strong in the current implementation:

- clear separation between frontend and backend
- persistent PostgreSQL-backed operational records
- media evidence saving
- optional local vs S3 object storage
- feed management from the admin panel
- detailed violation and challan review UI
- mock registry integration that simulates a future government data architecture

## 19. Current Limitations

Important limitations at the time of writing:

- the surveillance add-source workflow is still file-upload based
- no direct RTSP/CCTV registration flow exists yet
- no real DoTM integration exists
- some challan policy values still need final mapping
- a dedicated API smoke-test harness was not finalized because `httpx` is not yet installed in the backend dev environment

## 20. Recommended Next Steps

Recommended engineering next steps are:

- finalize fine policies for `plate_missing` and `plate_unreadable`
- add a proper automated API smoke-test layer
- add RTSP or managed remote camera registration
- strengthen accident ingestion if required for the deployment
- add authentication and access control for admin actions
- define a formal production data retention and audit policy

## 21. Conclusion

HawaiMama is currently a credible hackathon-grade traffic monitoring system with:

- a usable operator interface
- a Python backend that acts as the real system backend
- persistent records
- evidence handling
- a surveillance management workflow
- a mock government vehicle-registry integration layer

It is not a production-ready government enforcement platform yet, but it is structured in a way that can be demonstrated clearly now and extended later with more realistic integrations.
