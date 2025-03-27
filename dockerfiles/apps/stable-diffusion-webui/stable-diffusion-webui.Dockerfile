ARG FEDORA_VER=41
FROM pytorch-vision-dev-f${FEDORA_VER} AS build

# Distro packages for build depedencies
# rust, openssl to build huggingface/tokenizers
RUN --mount=type=cache,id=f${FEDORA_VER}-dnf5,target=/var/cache/libdnf5 \
	dnf5 install -y rust \
		cargo openssl-devel

# huggingface-tokenizers prep
# version matched with huggingface/transformers in stable-diffusion-webui/requirements_versions.txt
# Using patched version to fix building with rustc-1.85
RUN git clone https://github.com/scottt/huggingface-tokenizers.git
RUN cd huggingface-tokenizers && git checkout 0.13.3-rust-fix

# pydub prep
# Using patched version to fix audioop being removed from Pyton 3.13
RUN git clone https://github.com/scottt/pydub.git
RUN cd pydub && git checkout 0.25.1-python-3.13-fix

# huggingface-tokenizers build
# See huggingface-tokenizers/bindings/python/build-wheels.sh
RUN cd huggingface-tokenizers && \
	pushd tokenizers && cargo build && popd && \
	pushd bindings/python && uv pip install --system -U setuptools-rust setuptools wheel && \
	python setup.py bdist_wheel

# pydub build
RUN cd pydub && \
	python setup.py bdist_wheel

# Application Image
FROM pytorch-vision-dev-f${FEDORA_VER} AS stable-diffusion-webui

# libavif-devel for pillow-avif-plugin
# gpeftools for libtcmalloc.so for stable-diffusion-webui
RUN --mount=type=cache,id=f${FEDORA_VER}-dnf5,target=/var/cache/libdnf5 \
	dnf5 install -y libavif-devel \
		gperftools \
		tini \
		xdg-open

COPY --from=build huggingface-tokenizers/bindings/python/dist/tokenizers-*.whl /opt
COPY --from=build pydub/dist/pydub-*.whl /opt

RUN uv pip install --system /opt/*.whl
RUN rm -f /opt/*.whl

# AUTOMATIC1111/stable-diffusion-webui prep
# Use patched version to not install ROCm and work with the deps above
WORKDIR /opt
RUN git clone https://github.com/scottt/stable-diffusion-webui.git
RUN cd stable-diffusion-webui && \
	git fetch && \
	git checkout rust-1.85-python3.13-fix # upstream: v1.10.1

WORKDIR /opt/stable-diffusion-webui
RUN uv pip list
RUN printf 'torch==2.6.0a0+git90b83a9\ntorchvision==0.21.0+7af6987\n' >> requirements_versions.txt

RUN uv pip install --system audioop_lts -r requirements_versions.txt
RUN printf 'venv_dir=-\n' >> webui-user.sh

#RUN usermod -aG video root

COPY ./stable-diffusion-webui-run-pip.patch .
RUN patch -p1 < stable-diffusion-webui-run-pip.patch
COPY ./stable-diffusion-webui-skimage-measure-regionprops-doc.patch .
RUN cd /usr/local/lib64/python3.13/site-packages/skimage && \
	patch -p1 < /opt/stable-diffusion-webui/stable-diffusion-webui-skimage-measure-regionprops-doc.patch
CMD ["/usr/bin/tini", "/opt/stable-diffusion-webui/webui.sh", "--", "-f", "--skip-python-version-check"] 
