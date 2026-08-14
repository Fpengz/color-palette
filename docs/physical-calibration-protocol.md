# Chromix Physical Calibration Protocol

Protocol ID: `spectral-protocol-v1`
Status: ready for laboratory review
Scope: named resin, substrate, pigment/masterbatch system, process, and
surface finish only

This protocol is the entry gate for the calibrated spectral path. A completed
software test or a good RGB-model score cannot substitute for these records.

## Measurement contract

Every sample must record:

- material role, supplier/product identifier, lot, carrier/base resin, and
  exact concentration in declared units;
- substrate, sample-preparation method, process settings, conditioning state,
  thickness, opacity, gloss, and surface texture;
- instrument identifier and calibration-standard check;
- reflectance from 400–700 nm at 10 nm intervals, or a documented resampling
  plan for the instrument's native interval;
- illuminant, observer, geometry, and SCI/SCE mode for every derived Lab value;
- operator, timestamp, environment, replicate number, raw-file URI, and
  immutable sample/batch/recipe identifiers; and
- prediction, model/calibration versions, correction rounds, and acceptance
  decision.

The machine-readable record is defined by
[`app/data_contract.py`](../app/data_contract.py), with the external-storage
schema version `spectral-sample-v1`.

The repository validates this contract and provides spectral K/S, metamerism,
residual, uncertainty, and fallback-serving primitives. Those primitives are
not a calibration artifact: they remain outside the production claim until
the records and validation evidence below exist.

## Procedure

1. Calibrate the instrument according to the instrument manufacturer's
   procedure and record the standard check before the sample run.
2. Prepare the base and pigment/masterbatch using the named process. Record
   actual weighed quantities, not only nominal settings.
3. Produce and condition the sample at the declared thickness and surface
   finish. Reject samples with visible defects and record the rejection.
4. Measure at least three replicates at the declared geometry and SCI/SCE mode.
   Preserve the raw spectra and calculate the replicate mean and spread.
5. Repeat the ladder across the material lots and process conditions that the
   intended product scope must support.
6. Derive Lab values only with the declared illuminant and observer. Keep the
   full spectrum as the source measurement.
7. Link the sample to the prediction and correction history before deciding
   acceptance.

## Concentration ladders

Each supported material system needs a base/pure state where physically
meaningful and multiple intermediate concentrations. The ladder must expose
the range used by the optimizer; a single endpoint is not a tint-strength
calibration.

`app.spectral.fit_ks_ladder` fits wavelength-dependent K and S trends only
when scattering is measured or supplied by a validated model. It must not be
fed a display RGB value as a substitute for either coefficient.

## Validation gate

Before a calibration version can be used outside shadow mode, the owner must
attach:

- a repeatability report for instrument and sample preparation;
- a held-out split by time, material lot, and recipe family;
- product-specific Delta E00 tolerances and first-shot/tail-error limits;
- multiple-illuminant metamerism results where relevant;
- an uncertainty calibration report and out-of-domain test set; and
- sign-off identifying the supported material/process scope.

Until all artifacts exist, API responses must remain `uncalibrated` or
`pending`, and the fallback physical baseline must remain available.
