class TavernGame < Formula
  desc "CLI interactive fiction game — explore a fantasy tavern"
  homepage "https://github.com/zxuexingzhijie/chatbot"
  url "https://github.com/zxuexingzhijie/chatbot/archive/refs/tags/1.0.0.2.tar.gz"
  sha256 "c86561f9219f214fba2a39dc11b488f4dd765e76e99dd73cd4f1a268983e04e9"
  license "MIT"

  depends_on "python@3.12"

  # Rust-built wheels (jiter, pydantic-core) use @rpath dylib IDs with
  # minimal Mach-O header padding. preserve_rpath prevents Homebrew from
  # rewriting them to absolute paths that won't fit in the header.
  preserve_rpath

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
