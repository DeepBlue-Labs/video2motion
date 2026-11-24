PYTHON ?= .venv/bin/python
GMR_PY ?= vendor/gmr/.venv/bin/python

.PHONY: check model-check preview retarget
check:
	python3 scripts/validate_repository.py

model-check:
	$(PYTHON) scripts/validate_repository.py --model

preview:
	mkdir -p work/preview
	MUJOCO_GL=$${MUJOCO_GL:-egl} $(PYTHON) scripts/render_npz_preview.py work/npz/1_vc.npz work/preview/1_vc.mp4

retarget:
	GMR_PY="$(GMR_PY)" bash scripts/retarget.sh
