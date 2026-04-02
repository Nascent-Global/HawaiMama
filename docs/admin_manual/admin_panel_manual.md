# HawaiMama Admin Panel Manual

## 1. Purpose of This Manual

This manual is written for government office operators and administrators who need to use the HawaiMama traffic monitoring panel during demonstrations, daily review sessions, or controlled pilot use.

This document explains:

- what each section of the panel does
- how to watch surveillance feeds
- how to add, edit, and remove surveillance sources
- how to review violations
- how to issue challans
- what parts of the system are real and what parts are demo data

## 2. What the System Does

HawaiMama is a traffic monitoring dashboard with four main functions:

- show surveillance feeds
- detect selected traffic violations
- store evidence such as screenshots and short clips
- generate challans after review

The panel has four main sections:

- `Live surveillance`
- `Violation logs`
- `Accident logs`
- `Challan logs`

There is also a separate `Feed Admin` area for managing surveillance sources.

## 3. Important Demo Disclaimer

Some information shown by the panel is mock data for demonstration purposes.

Examples of demo-only or simulated data:

- vehicle owner details from the mock DoTM registry
- challan data generated from AI-detected violations
- accident records if no real accident detection is connected

When you see the message below, it means the record is not from a real government database:

`Demo data — not real DoTM records`

## 4. Before You Start

Make sure the following are running:

- the Python backend server
- the admin frontend
- the database service

If the panel opens correctly in the browser, you are ready to use it.

## 5. Main Dashboard Overview

When you open the main dashboard, you will see:

- a left navigation area
- a search bar
- a `System Output` toggle
- a `Feed Admin` button
- surveillance cards or log records depending on the selected section

### 5.1 Main Navigation Tabs

Use the left-side navigation to switch between:

- `Live surveillance`
- `Violation logs`
- `Accident logs`
- `Challan logs`

## 6. Live Surveillance

The `Live surveillance` tab is used to monitor all currently registered surveillance feeds.

Each card shows:

- feed identifier such as `NV1`, `NV2`, and so on
- location link
- live status indicator
- video preview

### 6.1 Raw Video and System Output

At the top right of the dashboard there is a `System Output` toggle.

When `System Output` is OFF:

- the system shows raw surveillance video
- this is the default mode
- it is lighter and faster
- it does not run full processing for all visible feed cards

When `System Output` is ON:

- feed cards show processed preview output where available
- if you open one specific feed, the system shows that feed’s live processed stream
- the processing mode depends on the feed’s admin configuration

### 6.2 Opening a Feed

To inspect a feed:

1. Go to `Live surveillance`
2. Click the feed card you want to inspect
3. The selected feed opens in a larger detailed view
4. Use the `< back` button to return to the grid

## 7. Feed Administration

Click `Feed Admin` from the dashboard to open the surveillance management panel.

This screen is used to:

- rename a feed location
- change a feed mode
- add a new surveillance source
- remove an existing surveillance source

### 7.1 Feed Modes

Each feed can be placed in one of two modes:

- `Enforcement mode`
- `Traffic light mode`

Use `Enforcement mode` for:

- speed-related monitoring
- helmet detection
- number plate recognition
- violation and challan workflows

Use `Traffic light mode` for:

- traffic flow monitoring
- signal-management-oriented viewing
- lower emphasis on violation enforcement

### 7.2 Changing a Feed Location or Mode

To edit a feed:

1. Open `Feed Admin`
2. Find the feed card you want to update
3. Change the display name in the location field
4. Select the operating mode
5. Click `Save changes`

If you want to cancel the edit:

- click `Reset`

### 7.3 Adding a New Surveillance Source

This is the current hackathon workflow for adding a new CCTV source.

What the operator does:

1. Open `Feed Admin`
2. Go to the `Add surveillance source` section
3. Enter the surveillance location
4. Select the default operating mode
5. Click `Choose raw video`
6. Select a video file from the computer
7. Click `Add surveillance feed`

What the system does:

- uploads the selected file to the backend
- stores it as the next feed in the surveillance registry
- creates a new feed ID such as `NV10`
- applies the location and selected mode
- shows the new feed in both the admin screen and the live dashboard

Important notes:

- this is a hackathon/demo workflow
- it is using uploaded video files, not direct live CCTV connections
- the selected file becomes a managed surveillance source inside the system

### 7.4 Removing a Surveillance Source

To remove a feed:

1. Open `Feed Admin`
2. Find the feed card
3. Click `Remove feed`
4. Confirm the action

What removal does:

- removes the surveillance source from the registry
- removes its preview/output artifacts used by the system
- removes it from the admin and live dashboard views

Use this carefully.

## 8. Violation Logs

The `Violation logs` section shows traffic violations that have been detected and stored by the backend.

Each record may include:

- owner name
- number plate
- location
- violation title
- timestamp
- evidence screenshot
- evidence clip

### 8.1 Opening a Violation

To inspect a violation:

1. Open `Violation logs`
2. Click `more detail`
3. Review:
   - plate number
   - owner or demo owner data
   - camera location
   - evidence screenshots
   - evidence video
   - violation description

### 8.2 Mock Owner Data

If owner information appears, it may come from the mock DoTM-style vehicle registry used for the demo.

If the detail page shows:

`Demo data — not real DoTM records`

then the owner information is simulated and should not be treated as a real official record.

### 8.3 Verifying a Violation

To approve a violation and issue a challan:

1. Open the violation detail
2. Review the evidence
3. Click `Verify & Generate Challan`

After verification:

- the record is marked verified
- a challan is generated
- the challan becomes visible in `Challan logs`

## 9. Accident Logs

The `Accident logs` section is reserved for accident review.

Important note:

- this area may still use demo or partial data depending on the current deployment
- use it for demonstration unless a real accident detection flow has been confirmed

## 10. Challan Logs

The `Challan logs` section shows generated challans.

Each challan includes:

- offender details
- vehicle details
- offense details
- amount to be paid
- evidence reference
- authority section

### 10.1 Opening a Challan

To inspect a challan:

1. Open `Challan logs`
2. Click `view challan`
3. Review the details

### 10.2 Printing a Challan

Inside challan detail:

1. Click `Print`
2. Use the browser print window to print or save as PDF

### 10.3 Demo Data Reminder

If a challan contains the note:

`Demo data — not real DoTM records`

then the owner/registry information came from the mock system used for demonstration.

## 11. Search and Filtering

Use the search bar to quickly find:

- feed IDs
- locations
- file names
- plate-related text in the live dashboard search area

In `Feed Admin`, use:

- the search field
- the mode filter buttons

to narrow the visible feeds.

## 12. Recommended Daily Demo Workflow

For a clean demonstration:

1. Open `Live surveillance`
2. Keep `System Output` OFF first to show raw surveillance
3. Turn `System Output` ON when explaining AI processing
4. Open one feed to show processed detail output
5. Switch to `Violation logs`
6. Open a violation and review its evidence
7. Verify the violation
8. Open `Challan logs`
9. Show the generated challan
10. Use `Feed Admin` if you need to demonstrate adding or removing surveillance sources

## 13. Troubleshooting

### 13.1 Feed Does Not Appear

Try:

- clicking `Refresh feeds` in `Feed Admin`
- checking that the backend server is running
- confirming that the surveillance upload completed successfully

### 13.2 Video Shows Raw Feed but Not Processed Feed

Check:

- whether `System Output` is enabled
- whether the feed is in `Enforcement mode` or `Traffic light mode`
- whether a processed preview is available for that feed

### 13.3 Violation Exists but Evidence Is Missing

Possible reasons:

- the clip or snapshot could not be generated at that moment
- the feed was removed
- the evidence storage backend is unavailable

### 13.4 Owner Data Looks Real but Should Be Treated as Demo Data

Always check for the disclaimer:

`Demo data — not real DoTM records`

## 14. Current Limitations

This hackathon version has some known limitations:

- surveillance sources are uploaded video files, not direct live CCTV hardware integrations
- mock DoTM data is not a real government registry
- some challan policy values are still pending update
- accident handling may still be partially simulated

## 15. Pending Policy Updates

The current pending tasks recorded in project documentation are:

- `plate_missing` challan/fine policy still needs final update
- `plate_unreadable` challan/fine policy still needs final update

## 16. Support Guidance

If an operator cannot complete a task:

- do not modify server files manually
- report the issue to the technical administrator
- share the feed ID, time, and the action that failed

This manual is intended for operational use. System-level configuration, storage, database behavior, and API details are documented separately in the technical report.
