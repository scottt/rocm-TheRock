ARG FEDORA_VER=42
FROM registry.fedoraproject.org/fedora-toolbox:$FEDORA_VER AS therock-dev-f42

######## Python and distro Packages #######
RUN --mount=type=cache,id=f${FEDORA_VER},target=/var/cache/dnf  \
	dnf5 install -y python python-devel \
		'@development-tools' clang gfortran \
		patchelf automake libtool perl \
		libglvnd-devel numactl-devel \
		libpng-devel libjpeg-turbo-devel libwebp-devel \
		pre-commit \
		fzf vim-enhanced

# lib{png,jpeg-turbo,webp} for pytorch-vision

ENV PATH="/usr/local/therock-tools/bin:$PATH"

######## Pip Packages ########
WORKDIR /therock-pip
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/bin/
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
WORKDIR /
RUN rm -rf /therock-pip

######## CCache ########
WORKDIR /install-ccache
COPY dockerfiles/install_ccache.sh ./
RUN ./install_ccache.sh "4.9"
WORKDIR /
RUN rm -rf /install-ccache

######## CMake ########
WORKDIR /install-cmake
ENV CMAKE_VERSION="3.25.2"
COPY dockerfiles/install_cmake.sh ./
RUN ./install_cmake.sh "${CMAKE_VERSION}"
WORKDIR /
RUN rm -rf /install-cmake

######## Ninja ########
WORKDIR /install-ninja
ENV NINJA_VERSION="1.12.1"
COPY dockerfiles/install_ninja.sh ./
RUN ./install_ninja.sh "${NINJA_VERSION}"
RUN echo 'Ninja install successful'
WORKDIR /
RUN rm -r /install-ninja

######## Google test: requires CMake, Ninja, distro C++ compiler #######
WORKDIR /install-googletest
ENV GOOGLE_TEST_VERSION="1.16.0"
COPY dockerfiles/install_googletest.sh ./
RUN ./install_googletest.sh "${GOOGLE_TEST_VERSION}"
WORKDIR /
RUN rm -rf /install-googletest

RUN printf "export PATH=/usr/local/therock-tools/bin:$PATH\n" > /etc/profile.d/therock-dev.sh
