ARG FEDORA_VER=41
FROM pytorch-dev-f${FEDORA_VER} AS build

# pytorch-vision-prep
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	if [ ! -d /therock/pytorch-vision ]; then git clone https://github.com/pytorch/vision.git /therock/pytorch-vision; fi && \
	cd /therock/pytorch-vision &&  \
	git checkout v0.21.0 # match pytorch version

# Development deps: https://github.com/pytorch/vision/blob/main/CONTRIBUTING.md#other-development-dependencies-some-of-these-are-needed-to-run-tests
RUN uv pip install --system \
	'setuptools>=62.3.0,<75.9' wheel \
	expecttest flake8 typing mypy pytest pytest-mock scipy requests

# pytorch-vision-build
# 	the `git clean -f` fixes a
# multiple definition of `vision::cuda_version` problem causd by double hipfiy
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	cd /therock/pytorch-vision && \
	git clean -f && \
	python setup.py bdist_wheel

RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	rm -f /opt/torchvision-*.whl && \
	cp $(ls -t /therock/pytorch-vision/dist/torchvision-*.whl | head -n 1) /opt

# Development image
FROM pytorch-dev-f${FEDORA_VER} AS pytorch-vision-dev-f${FEDORA_VER}
COPY --from=build /opt/torchvision-*.whl /opt
RUN uv pip install --system /opt/*.whl
