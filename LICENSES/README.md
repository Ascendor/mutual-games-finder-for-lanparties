# Third-party licenses

This directory contains:

- standard license texts used by project dependencies;
- project-specific license copies for material references;
- exact package/version/license inventories for backend and frontend.
- CycloneDX 1.5 software bills of materials (`*.cdx.json`).

`backend-dependencies.tsv` reflects the Python environment captured for this
release. `frontend-dependencies.tsv` reflects all packages in
`frontend/package-lock.json`, including platform-specific build packages that
are not shipped in the browser bundle.

After a dependency update, regenerate both inventories with the scripts in
`scripts/` and review new or changed licenses before publishing a release.
Generated `backend-dependency-licenses.txt` and
`frontend-dependency-licenses.txt` files collect package-specific license and
notice files when the dependency trees are installed.

Container base images and the PostgreSQL image also include operating-system
packages under their own licenses. Their package notices remain available
inside the respective images.
