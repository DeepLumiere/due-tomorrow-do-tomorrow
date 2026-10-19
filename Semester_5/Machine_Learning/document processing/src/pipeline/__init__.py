"""
Pipeline package initialization.
Configures Windows environment flags and symlink fallbacks for Hugging Face Hub.
"""
import os
import shutil

# Suppress Hugging Face symlink warning on Windows non-admin
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Monkeypatch huggingface_hub _create_symlink to fallback to direct file copy on Windows (WinError 1314)
try:
    import huggingface_hub.file_download as _hf_fd
    _orig_create_symlink = _hf_fd._create_symlink

    def _safe_create_symlink(src: str, dst: str, new_blob: bool = False) -> None:
        try:
            _orig_create_symlink(src, dst, new_blob=new_blob)
        except OSError:
            abs_src = os.path.abspath(os.path.expanduser(src))
            abs_dst = os.path.abspath(os.path.expanduser(dst))
            os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
            try:
                os.remove(abs_dst)
            except OSError:
                pass
            if new_blob:
                shutil.move(abs_src, abs_dst)
            else:
                shutil.copyfile(abs_src, abs_dst)

    _hf_fd._create_symlink = _safe_create_symlink
except Exception:
    pass
