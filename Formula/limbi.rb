class Limbi < Formula
  include Language::Python::Virtualenv

  desc "Omni-Agent orchestration platform for local and cloud LLM workflows"
  homepage "https://github.com/sayon999-d/Limbi-"
  url "https://files.pythonhosted.org/packages/f4/78/e30792ed0993c30e393c2fbaad9aeca0e384c53d7eb6e90366d25376e3d2/limbi-1.7.4.tar.gz"
  sha256 "dfbe2c35a42bcc074421791dd66775eb46c1c4585cfe5e27bede53d2fd478033"
  license "Apache-2.0"

  depends_on "python@3.11"
  depends_on "git"
  depends_on "ripgrep"
  depends_on "ffmpeg"

  resource "langchain-core" do
    url "https://files.pythonhosted.org/packages/1f/01/4771b7ab2af1d1aba5b710bd8f13d9225c609425214b357590a17b01be77/langchain_core-1.3.3-py3-none-any.whl"
    sha256 "18aae8506f37da7f74398492279a7d6efcee4f8e23c4c41c7af080eeb7ef7bd1"
  end

  resource "langchain-ollama" do
    url "https://files.pythonhosted.org/packages/2c/b2/c2acb076590a98bee2816ed5f285e00df162a34238f9e276e175e14ebc35/langchain_ollama-1.1.0-py3-none-any.whl"
    sha256 "43ac83a6eacb0f43855810739794dd55019e0d9b17bdcf3ecb3b1991ac3b59dd"
  end

  resource "langchain-protocol" do
    url "https://files.pythonhosted.org/packages/1d/7a/9c97a7b9cbe4c5dc6a44cdb1545450c28f0c8ce89b9c1f0ee7fbad896263/langchain_protocol-0.0.15-py3-none-any.whl"
    sha256 "461eb794358f83d5e42635a5797799ffec7b4702314e34edf73ac21e75d3ef79"
  end

  resource "langsmith" do
    url "https://files.pythonhosted.org/packages/f4/76/53033db34ffccd25d62c32b23b9468f7228b455da6976e1c420ae31555c4/langsmith-0.7.33-py3-none-any.whl"
    sha256 "5b535b991d52d3b664ebb8dc6f95afcf8d0acb42e062ac45a54a6a4820139f20"
  end

  resource "jsonpatch" do
    url "https://files.pythonhosted.org/packages/73/07/02e16ed01e04a374e644b575638ec7987ae846d25ad97bcc9945a3ee4b0e/jsonpatch-1.33-py2.py3-none-any.whl"
    sha256 "0ae28c0cd062bbd8b8ecc26d7d164fbbea9652a1a3693f3b956c1eae5145dade"
  end

  resource "packaging" do
    url "https://files.pythonhosted.org/packages/88/ef/eb23f262cca3c0c4eb7ab1933c3b1f03d021f2c48f54763065b6f0e321be/packaging-24.2-py3-none-any.whl"
    sha256 "09abb1bccd265c01f4a3aa3f7a7db064b36514d2cba19a2f694fe6150451a759"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/f3/0a/fd7d723f8f8153418fb40cf9c940e82004fce7e987026b08a68a36dd3fe7/pydantic-2.13.3-py3-none-any.whl"
    sha256 "6db14ac8dfc9a1e57f87ea2c0de670c251240f43cb0c30a5130e9720dc612927"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/16/19/13de8e4377ed53079ee996e1ab0a9c33ec2faf808a4647b7b4c0d46dd239/pyyaml-6.0.3-cp311-cp311-macosx_11_0_arm64.whl"
    sha256 "652cb6edd41e718550aad172851962662ff2681490a8a711af6a4d288dd96824"
  end

  resource "tenacity" do
    url "https://files.pythonhosted.org/packages/e5/30/643397144bfbfec6f6ef821f36f33e57d35946c44a2352d3c9f0ae847619/tenacity-9.1.2-py3-none-any.whl"
    sha256 "f77bf36710d8b73a50b2dd155c97b870017ad21afe6ab300326b0371b3b05138"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/18/67/36e9267722cc04a6b9f15c7f3441c2363321a3ea07da7ae0c0707beb2a9c/typing_extensions-4.15.0-py3-none-any.whl"
    sha256 "f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548"
  end

  resource "uuid-utils" do
    url "https://files.pythonhosted.org/packages/43/b7/add4363039a34506a58457d96d4aa2126061df3a143eb4d042aedd6a2e76/uuid_utils-0.14.1-cp39-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl"
    sha256 "93a3b5dc798a54a1feb693f2d1cb4cf08258c32ff05ae4929b5f0a2ca624a4f0"
  end

  resource "ollama" do
    url "https://files.pythonhosted.org/packages/c4/ab/d6722beeb2d10f7a3b9ff49375708904fde18f82b5609a0bc4aeb5996a4d/ollama-0.6.2-py3-none-any.whl"
    sha256 "3ad7daab28e5a973445c36a73882a3ef698c2ebb00e21e308652741577509f7d"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/94/54/e7d793b573f298e1c9013b8c4dade17d481164aa517d1d7148619c2cedbf/markdown_it_py-4.0.0-py3-none-any.whl"
    sha256 "87327c59b172c5011896038353a81343b6754500a08cd7a4973bb48c6d578147"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/c7/21/705964c7812476f378728bdf590ca4b771ec72385c533964653c68e86bdc/pygments-2.19.2-py3-none-any.whl"
    sha256 "86540386c03d588bb81d44bc3928634ff26449851e99741617ecb9037ee5ec0b"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/98/78/01c019cdb5d6498122777c1a43056ebb3ebfeef2076d9d026bfe15583b2b/click-8.3.1-py3-none-any.whl"
    sha256 "981153a64e25f12d547d3426c367a4857371575ee7ad18df2a6183ab0545b2a6"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/25/7a/b0178788f8dc6cafce37a212c99565fa1fe7872c70c6c9c1e1a372d9d88f/rich-14.2.0-py3-none-any.whl"
    sha256 "76bc51fe2e57d2b1be1f96c524b890b816e334ab4c1e45888799bfaab0021edd"
  end

  resource "python-dotenv" do
    url "https://files.pythonhosted.org/packages/14/1b/a298b06749107c305e1fe0f814c6c74aea7b2f1e10989cb30f544a1b3253/python_dotenv-1.2.1-py3-none-any.whl"
    sha256 "b81ee9561e9ca4004139c6cbba3a238c32b03e4894671e181b671e8cb8425d61"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/56/95/9377bcb415797e44274b51d46e3249eba641711cf3348050f76ee7b15ffc/httpx-0.27.2-py3-none-any.whl"
    sha256 "7bb2708e112d8fdd7829cd4243970f0c223274051cb35ee80c03301ee29a3df0"
  end

  resource "requests" do
    url "https://files.pythonhosted.org/packages/7c/e4/56027c4a6b4ae70ca9de302488c5ca95ad4a39e190093d6c1a8ace08341b/requests-2.32.4-py3-none-any.whl"
    sha256 "27babd3cda2a6d50b30443204ee89830707d396671944c998b5975b031ac2b2c"
  end

  resource "requests-toolbelt" do
    url "https://files.pythonhosted.org/packages/3f/51/d4db610ef29373b879047326cbf6fa98b6c1969d6f6dc423279de2b1be2c/requests_toolbelt-1.0.0-py2.py3-none-any.whl"
    sha256 "cccfdd665f0a24fcf4726e690f65639d272bb0637b9b92dfd91a5568ccf6bd06"
  end

  resource "anyio" do
    url "https://files.pythonhosted.org/packages/7f/9c/36c5c37947ebfb8c7f22e0eb6e4d188ee2d53aa3880f3f2744fb894f0cb1/anyio-4.12.0-py3-none-any.whl"
    sha256 "dad2376a628f98eeca4881fc56cd06affd18f659b17a747d3ff0307ced94b1bb"
  end

  resource "certifi" do
    url "https://files.pythonhosted.org/packages/70/7d/9bc192684cea499815ff478dfcdc13835ddf401365057044fb721ec6bddb/certifi-2025.11.12-py3-none-any.whl"
    sha256 "97de8790030bbd5c2d96b7ec782fc2f7820ef8dba6db909ccf95449f2d062d4b"
  end

  resource "httpcore" do
    url "https://files.pythonhosted.org/packages/7e/f5/f66802a942d491edb555dd61e3a9961140fd64c90bce1eafd741609d334d/httpcore-1.0.9-py3-none-any.whl"
    sha256 "2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/0e/61/66938bbb5fc52dbdf84594873d5b51fb1f7c7794e9c0f5bd885f30bc507b/idna-3.11-py3-none-any.whl"
    sha256 "771a87f49d9defaf64091e6e6fe9c18d4833f140bd19464795bc32d966ca37ea"
  end

  resource "sniffio" do
    url "https://files.pythonhosted.org/packages/e9/44/75a9c9421471a6c4805dbf2356f7c181a29c1879239abab1ea2cc8f38b40/sniffio-1.3.1-py3-none-any.whl"
    sha256 "2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2"
  end

  resource "charset-normalizer" do
    url "https://files.pythonhosted.org/packages/0a/4c/925909008ed5a988ccbb72dcc897407e5d6d3bd72410d69e051fc0c14647/charset_normalizer-3.4.4-py3-none-any.whl"
    sha256 "7a32c560861a02ff789ad905a2fe94e3f840803362c84fecf1851cb4cf3dc37f"
  end

  resource "urllib3" do
    url "https://files.pythonhosted.org/packages/6d/b9/4095b668ea3678bf6a0af005527f39de12fb026516fb3df17495a733b7f8/urllib3-2.6.2-py3-none-any.whl"
    sha256 "ec21cddfe7724fc7cb4ba4bea7aa8e2ef36f607a4bab81aa6ce42a13dc3f03dd"
  end

  resource "annotated-types" do
    url "https://files.pythonhosted.org/packages/78/b6/6307fbef88d9b5ee7421e68d78a9f162e0da4900bc5f5793f6d3d0e34fb8/annotated_types-0.7.0-py3-none-any.whl"
    sha256 "1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53"
  end

  resource "pydantic-core" do
    url "https://files.pythonhosted.org/packages/b6/f6/99ae893c89a0b9d3daec9f95487aa676709aa83f67643b3f0abaf4ab628a/pydantic_core-2.46.3-cp311-cp311-macosx_11_0_arm64.whl"
    sha256 "cca67d52a5c7a16aed2b3999e719c4bcf644074eac304a5d3d62dd70ae7d4b2c"
  end

  resource "typing-inspection" do
    url "https://files.pythonhosted.org/packages/dc/9b/47798a6c91d8bdb567fe2698fe81e0c6b7cb7ef4d13da4114b41d239f65d/typing_inspection-0.4.2-py3-none-any.whl"
    sha256 "4ed1cacbdc298c220f1bd249ed5287caa16f34d44ef4e9c3d0cbad5b521545e7"
  end

  resource "jsonpointer" do
    url "https://files.pythonhosted.org/packages/9e/6a/a83720e953b1682d2d109d3c2dbb0bc9bf28cc1cbc205be4ef4be5da709d/jsonpointer-3.1.1-py3-none-any.whl"
    sha256 "8ff8b95779d071ba472cf5bc913028df06031797532f08a7d5b602d8b2a488ca"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl"
    sha256 "84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8"
  end

  resource "h11" do
    url "https://files.pythonhosted.org/packages/04/4b/29cac41a4d98d144bf5f6d33995617b185d14b22401f75ca86f384e87ff1/h11-0.16.0-py3-none-any.whl"
    sha256 "63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86"
  end

  resource "exceptiongroup" do
    url "https://files.pythonhosted.org/packages/36/f4/c6e662dade71f56cd2f3735141b265c3c79293c109549c1e6933b0651ffc/exceptiongroup-1.3.0-py3-none-any.whl"
    sha256 "4d111e6e0c13d0644cad6ddaa7ed0261a0b36971f6d23e7ec9b4b9097da78a10"
  end

  resource "orjson" do
    url "https://files.pythonhosted.org/packages/7a/a2/21b25ce4a2c71dbb90948ee81bd7a42b4fbfc63162e57faf83157d5540ae/orjson-3.10.15-cp311-cp311-macosx_10_15_x86_64.macosx_11_0_arm64.macosx_10_15_universal2.whl"
    sha256 "c4cc83960ab79a4031f3119cc4b1a1c627a3dc09df125b27c4201dff2af7eaa6"
  end

  resource "xxhash" do
    url "https://files.pythonhosted.org/packages/8c/0c/7c3bc6d87e5235672fcc2fb42fd5ad79fe1033925f71bf549ee068c7d1ca/xxhash-3.5.0-cp311-cp311-macosx_11_0_arm64.whl"
    sha256 "6027dcd885e21581e46d3c7f682cfb2b870942feeed58a21c29583512c3f09f8"
  end

  resource "zstandard" do
    url "https://files.pythonhosted.org/packages/e8/46/66d5b55f4d737dd6ab75851b224abf0afe5774976fe511a54d2eb9063a41/zstandard-0.23.0-cp311-cp311-macosx_11_0_arm64.whl"
    sha256 "77ea385f7dd5b5676d7fd943292ffa18fbf5c72ba98f7d09fc1fb9e819b34c23"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "limbi", shell_output("#{bin}/limbi --version")
  end
end
