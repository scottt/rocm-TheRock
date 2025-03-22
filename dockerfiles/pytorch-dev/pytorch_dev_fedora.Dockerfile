ARG FEDORA_VER=41
FROM rocm-dev-f${FEDORA_VER} AS build

# pytorch-fetch
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	mkdir -p /therock/pytorch

RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	--mount=type=bind,target=/therock/src,rw \
	python3 /therock/src/external-builds/pytorch/ptbuild.py \
		checkout \
		--repo /therock/pytorch \
		--depth 1 \
		--jobs 10 \
		--no-patch \
		--no-hipify

# pytorch-prep
# for `git am`
RUN git config --global user.email "you@example.com" && \
    git config --global user.name "Your Name"

RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	--mount=type=bind,target=/therock/src,rw \
	python3 /therock/src/external-builds/pytorch/ptbuild.py \
		checkout \
		--repo /therock/pytorch  \
		--depth 1  \
		--jobs 10

# pytorch-build
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	cd /therock/pytorch && \
	uv pip install --system -r requirements.txt

ENV CMAKE_PREFIX_PATH=/opt/rocm
ENV USE_KINETO=OFF
ENV PYTORCH_ROCM_ARCH=$AMDGPU_TARGETS

RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	cd /therock/pytorch && \
	python setup.py build --cmake-only && \
	pushd build && cmake "-DPYTORCH_ROCM_ARCH=$AMDGPU_TARGETS" . && popd && \
	python setup.py bdist_wheel

# pytorch-install
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	uv pip install --system $(ls -tr /therock/pytorch/dist/torch-*.whl | head -n 1)

# Export artifacts
FROM registry.fedoraproject.org/fedora-toolbox:$FEDORA_VER AS artifacts
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	cp $(ls -tr /therock/pytorch/dist/torch-*.whl | head -n 1) /

# Development image
FROM rocm-dev-f${FEDORA_VER} AS pytorch-dev-f${FEDORA_VER}
COPY --from=artifacts /*.whl /opt/
RUN uv pip install --system /opt/*.whl
