ARG FEDORA_VER=42
FROM registry.fedoraproject.org/fedora-toolbox:$FEDORA_VER AS pytorch-dev-f42

######## Python and distro Packages #######
RUN --mount=type=cache,id=f${FEDORA_VER},target=/var/cache/dnf  \
	dnf5 install -y python python-devel \
		'@development-tools' clang gfortran \
		patchelf automake libtool perl \
		libglvnd-devel numactl-devel \
		libpng-devel libjpeg-turbo-devel libwebp-devel \
		pre-commit \
		fzf vim-enhanced \
		cmake \
		ccache \
		ninja

######## Google test: requires CMake, Ninja, distro C++ compiler #######
WORKDIR /install-googletest
ENV GOOGLE_TEST_VERSION="1.16.0"
COPY dockerfiles/install_googletest.sh ./
RUN ./install_googletest.sh "${GOOGLE_TEST_VERSION}"
WORKDIR /
RUN rm -rf /install-googletest
