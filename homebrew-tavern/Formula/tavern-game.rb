class TavernGame < Formula
  include Language::Python::Virtualenv

  desc "CLI interactive fiction game — explore a fantasy tavern"
  homepage "https://github.com/zxuexingzhijie/chatbot"
  url "https://github.com/zxuexingzhijie/chatbot/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.12"

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/pydantic/pydantic-2.11.3.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pydantic-core" do
    url "https://files.pythonhosted.org/packages/pydantic-core/pydantic_core-2.33.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/rich/rich-13.9.4.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/pyyaml/PyYAML-6.0.2.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "tenacity" do
    url "https://files.pythonhosted.org/packages/tenacity/tenacity-9.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "openai" do
    url "https://files.pythonhosted.org/packages/openai/openai-1.82.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/markdown-it-py/markdown_it_py-3.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/mdurl/mdurl-0.1.2.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/pygments/pygments-2.19.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/typing-extensions/typing_extensions-4.13.2.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "annotated-types" do
    url "https://files.pythonhosted.org/packages/annotated-types/annotated_types-0.7.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "tavern", shell_output("#{bin}/tavern --help")
  end
end
