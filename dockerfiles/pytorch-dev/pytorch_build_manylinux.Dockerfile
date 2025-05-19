FROM rocm-manylinux-gfx1151:6.4.0rc AS pytorch-build-manylinux-gfx1151:6.4.0rc

# See pytorch Dockerfile_2_28 (which uses manylinux 2.28)
# Ensure the expected devtoolset is used
ARG DEVTOOLSET_VERSION=12
ENV PATH=/opt/rh/gcc-toolset-${DEVTOOLSET_VERSION}/root/usr/bin:$PATH
ENV LD_LIBRARY_PATH=/opt/rh/gcc-toolset-${DEVTOOLSET_VERSION}/root/usr/lib64:/opt/rh/gcc-toolset-${DEVTOOLSET_VERSION}/root/usr/lib:$LD_LIBRARY_PATH
ENV LDFLAGS="-Wl,-rpath=/opt/rh/gcc-toolset-${DEVTOOLSET_VERSION}/root/usr/lib64 -Wl,-rpath=/opt/rh/gcc-toolset-${DEVTOOLSET_VERSION}/root/usr/lib"

######## Python and distro Packages #######
RUN --mount=type=cache,id=therock_build_manylinux_x86_main,target=/var/cache/dnf \
        dnf install -y \
                passwd \
                sudo \
                fzf \
                elfutils \
                xz-devel \
                wget \
                curl \
                perl \
                util-linux \
                bzip2 \
                git \
                patch \
                which \
                perl \
                zlib-devel \
                gcc-toolset-${DEVTOOLSET_VERSION}

RUN --mount=type=cache,id=therock_build_manylinux_x86_main,target=/var/cache/dnf \
        dnf remove -y gcc

ENV PYTHON_BIN_DIR=/opt/python/cp311-cp311/bin
ENV PYTHON=${PYTHON_BIN_DIR}/python3.11
ENV PATH=$PYTHON_BIN_DIR:$PATH

#RUN ${PYTHON} -V
#RUN g++ --version
#RUN which g++

RUN mkdir -p /w
RUN mkdir -p /o

RUN printf "export PATH=/opt/rocm/bin:\$PATH\n" > /etc/profile.d/rocm.sh
# RUN printf "source /opt/rh/gcc-toolset-${DEVTOOLSET_VERSION}/enable\n" > /etc/profile.d/99-pytorch-build.sh
RUN printf "export PS1='pytorch-build:\W$ '" > /etc/profile.d/ps1.sh
