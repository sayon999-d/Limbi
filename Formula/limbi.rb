class Limbi < Formula
  include Language::Python::Virtualenv

  desc "Omni-Agent orchestration platform for local and cloud LLM workflows"
  homepage "https://github.com/sayon999-d/Limbi-"
  url "https://files.pythonhosted.org/packages/source/l/limbi/limbi-1.6.3.tar.gz"
  sha256 "e3a6b577a59057608b85dd6b205a4ae02770417b3b9ceee2420d9fa73799eb0f"
  license "Apache-2.0"

  depends_on "python@3.11"
  depends_on "git"
  depends_on "ripgrep"
  depends_on "ffmpeg"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "limbi", shell_output("#{bin}/limbi --version")
  end
end
