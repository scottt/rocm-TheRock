ARG FEDORA_VER=41
FROM registry.fedoraproject.org/fedora-toolbox:$FEDORA_VER AS builddeps

######## Python and distro Packages #######
RUN --mount=type=cache,id=f${FEDORA_VER},target=/var/cache/dnf  \
	dnf5 install -y python python-devel \
		'@development-tools' clang gfortran \
		patchelf vim-enhanced git-lfs automake perl \
		libglvnd-devel numactl-devel \
		libpng-devel libjpeg-turbo-devel libwebp-devel # For pytorch-vision

######## Pip Packages ########
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/bin/
RUN uv pip install --system CppHeaderParser==2.7.4 meson==1.7.0 tomli==2.2.1 PyYAML==6.0.2

######## CCache ########
WORKDIR /install-ccache
COPY dockerfiles/cpubuilder/install_ccache.sh ./
RUN ./install_ccache.sh "4.9"
WORKDIR /
RUN rm -rf /install-ccache

######## CMake ########
WORKDIR /install-cmake
ENV CMAKE_VERSION="3.25.2"
COPY dockerfiles/cpubuilder/install_cmake.sh ./
RUN ./install_cmake.sh "${CMAKE_VERSION}"
WORKDIR /
RUN rm -rf /install-cmake

######## Ninja ########
WORKDIR /install-ninja
ENV NINJA_VERSION="1.12.1"
COPY dockerfiles/cpubuilder/install_ninja.sh ./
RUN ./install_ninja.sh "${NINJA_VERSION}"
RUN echo 'Ninja install successful'
WORKDIR /
RUN rm -r /install-ninja

######## Google test: requires CMake, Ninja, distro C++ compiler #######
WORKDIR /install-googletest
ENV GOOGLE_TEST_VERSION="1.16.0"
COPY dockerfiles/cpubuilder/install_googletest.sh ./
RUN ./install_googletest.sh "${GOOGLE_TEST_VERSION}"
WORKDIR /
RUN rm -rf /install-googletest

FROM builddeps AS build

######## GIT CONFIGURATION ########
# Git started enforcing strict user checking, which thwarts version
# configuration scripts in a docker image where the tree was checked
# out by the host and mapped in. Disable the check.
# See: https://github.com/openxla/iree/issues/12046
# We use the wildcard option to disable the checks. This was added
# in git 2.35.3
RUN git config --global --add safe.directory '*'

# therock-prep
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	mkdir -p /therock/src && \
	mkdir -p /therock/output

# therock-build
ENV AMDGPU_TARGETS=gfx1151
ENV THEROCK_INTERACTIVE=1
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	--mount=type=bind,target=/therock/src,rw \
	/therock/src/build_tools/detail/linux_portable_build_in_container.sh \
		-DTHEROCK_AMDGPU_FAMILIES="${AMDGPU_TARGETS}" \
		-DTHEROCK_VERBOSE=on && \
	cmake --build /therock/output/build --target therock-archives

# Export artifacts
# Can't use `FROM scratch` here due to needing `sh` to use RUN and the cache mount
FROM registry.fedoraproject.org/fedora-toolbox:$FEDORA_VER AS artifacts
RUN --mount=type=cache,id=pytorch-f${FEDORA_VER},target=/therock \
	tar -C /therock/output/build/dist/rocm -cJf /therock-${AMDGPU_TARGETS}-$(date +'%Y%m%d').tar.xz . && \
	cp /therock/output/build/artifacts/*.tar.xz /

# Development image
FROM builddeps AS rocm-dev-f${FEDORA_VER}
COPY --from=artifacts /therock-*.tar.xz /opt

RUN mkdir -p /opt/rocm && \
	tar -C /opt/rocm -xJf /opt/therock-*.tar.xz && \
	rm -f /opt/*.tar.xz
	
RUN printf '/opt/rocm/lib\n/opt/rocm/lib/rocm_sysdeps/lib\n' > /etc/ld.so.conf.d/rocm.conf && \
	ldconfig -v
RUN printf "export PATH=/opt/rocm/bin:$PATH\n" > /etc/profile.d/rocm.sh
