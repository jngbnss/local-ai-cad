from app.ai.diagnostics import collect_diagnostics

REQUIRED_FIELDS = {
    "python_version",
    "python_executable",
    "torch_version",
    "torch_cuda_version",
    "cuda_available",
    "device_name",
    "device_capability",
    "total_vram_mib",
    "driver_version",
}


def test_report_contains_every_required_field():
    report = collect_diagnostics()

    assert REQUIRED_FIELDS <= report.keys()
    assert isinstance(report["cuda_available"], bool)


def test_cuda_report_is_self_consistent():
    """CUDA 가능/불가 두 경우 모두 사용자가 원인을 볼 수 있어야 한다."""
    report = collect_diagnostics()

    if report["cuda_available"]:
        assert report["device_name"]
        assert report["total_vram_mib"] > 0
        assert report["torch_cuda_version"] is not None
    else:
        # 불가일 때는 조치 가능한 힌트가 반드시 따라붙는다.
        assert report["cuda_unavailable_hint"]
