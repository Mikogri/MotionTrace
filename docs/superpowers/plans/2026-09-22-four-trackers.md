# Four independent trackers — implementation plan

Goal: one Analyze schedules DINO/SAM, SAMURAI, TAPNext++ and BootsTAPIR; switching only selects an already prepared result. User specification: attachment947a5e75-388d-4c22-86cd-904557b2c887.

Architecture: preserve RTMPose/oldresults/customweights. Shared explicit physical target and pose/exercise preparation; independent subprocess adapters and states; resource-budgeted queue. Schema4 observations remain compatible; versioned session manifest tracks statuses/provenance. C# prepares and persists complete movement/chart snapshots before Ready, exposes a memory-only ActiveProvider selection. Nativevideo source unchanged.

Audit: no Git repository, so no gitdiff/commit possible; avoid unrelated changes. RTX3070Ti8GB; initial free6755MiB. Existing Python motiontrace(MMPose) and motiontrace-vision untouched. Existing WinUI net10 and testbaseline314passing at previous task. Current ownshaft model preserved but excluded from comparison.

- [x] Verify and install pinned official SAMURAI and TAPNext++/BootsTAPIR, license/checksum receipts; separate environments.
- [x] Tests and real adapters: exact timestamps/coordinates, rawvisibility, no inventedobservations; boundedbuffers preservingtemporalstate.
- [x] Python commonpreparation, initialization validation, independent resourcequeue/cancellation/cache and offlineprocessprotocol.
- [x] C# sessioncontracts/processreader/precomputedmetrics/cache and memory-only selection tests.
- [x] WinUI four-statusselector, point/boxinitialization, atomicchart/overlay change preservingplayback, spinnerbesideAnalyze, retry/missingactions.
- [x] CPUcontracttests, realGPUinference eachmodel, fullsession failure/cancellation/reopen, build/smoke/latencymeasurement; reportlimitations honestly.

Execution: independent bounded agents own SAMURAI, TAP backends, C#sessioninfra; root owns Pythonorchestrator andWinUIintegration. GPU tests serialized untilactualbudgetmeasurements supportconcurrency. Noautomaticproviderfallback, no newRPE, no generatedplaybackvideos.
