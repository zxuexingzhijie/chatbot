class TavernGame < Formula
  desc "CLI interactive fiction game — explore a fantasy tavern"
  homepage "https://github.com/zxuexingzhijie/chatbot"
  url "https://github.com/zxuexingzhijie/chatbot/archive/refs/tags/1.0.0.1.tar.gz"
  sha256 "bb5c784736c0f87b8e8604ab49967b684ebeccb586d00284bf5b60599864d218"
  license "MIT"

  depends_on "python@3.12"

  def install
    python3 = "python3.12"
    venv = libexec
    system python3, "-m", "venv", venv.to_s
    system venv/"bin/pip", "install", "--upgrade", "pip"
    system venv/"bin/pip", "install", "--no-cache-dir", buildpath.to_s
    bin.install_symlink venv/"bin/tavern"
  end

  test do
    assert_match "tavern", shell_output("#{bin}/tavern --help")
  end
end
