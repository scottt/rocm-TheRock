FROM ghcr.io/rocm/therock_build_manylinux_x86_64:main AS build
ARG AMDGPU_TARGETS

######## Python and distro Packages #######
RUN --mount=type=cache,id=therock_build_manylinux_x86_main,target=/var/cache/dnf \
	dnf install -y jq

COPY dockerfiles/pytorch-dev/install_rocm_from_release.sh /

RUN --mount=type=cache,id=therock_artifacts,target=/rocm-tarballs \
	INSTALL_PREFIX=/opt/rocm bash \
	/install_rocm_from_release.sh "$AMDGPU_TARGETS"

# Development image
FROM ghcr.io/rocm/therock_build_manylinux_x86_64:main AS rocm-manylinux

COPY --from=build /opt/rocm /opt
RUN printf '/opt/rocm/lib\n/opt/rocm/lib/rocm_sysdeps/lib\n' > /etc/ld.so.conf.d/rocm.conf && \
	ldconfig -v
RUN printf "export PATH=/opt/rocm/bin:$PATH\n" > /etc/profile.d/rocm.sh
RUN printf "export PS1='rocm_manylinux:\W$ '" > /etc/profile.d/ps1.sh
