import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.modules.data_pipeline import sync_runner, failure_handler, checkpoint_manager

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_bq():
    return MagicMock()

@pytest.mark.asyncio
async def test_failure_handler_retries_and_fails():
    """Test that failure handler retries 3 times and returns False on persistent failure."""
    fail_mock = AsyncMock(side_effect=Exception("Test error"))
    
    with patch("app.modules.data_pipeline.failure_handler._RETRY_DELAYS_SECONDS", [0, 0, 0]):
        success, attempts, error = await failure_handler.run_with_retry(
            fail_mock,
            stage_name="TEST_STAGE",
            pipeline_run_id="run_123",
        )
    
    assert success is False
    assert attempts == 3
    assert error == "Test error"
    assert fail_mock.call_count == 3

@pytest.mark.asyncio
async def test_failure_handler_succeeds_after_retry():
    """Test that failure handler returns True if it succeeds on a subsequent attempt."""
    call_count = 0
    
    async def _flakey_stage():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Temporary error")
        return True

    with patch("app.modules.data_pipeline.failure_handler._RETRY_DELAYS_SECONDS", [0, 0, 0]):
        success, attempts, error = await failure_handler.run_with_retry(
            _flakey_stage,
            stage_name="TEST_STAGE",
            pipeline_run_id="run_123",
        )
        
    assert success is True
    assert attempts == 3
    assert error == ""

@pytest.mark.asyncio
async def test_checkpoint_manager_uses_last_successful(mock_db):
    """Test that checkpoint manager picks up the end time of the last successful run."""
    last_end = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    with patch("app.modules.data_pipeline.repository.get_last_successful_run", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"checkpoint_end": last_end}
        
        start, end = await checkpoint_manager.get_checkpoint_window(mock_db, store_id="store_1")
        
        assert start == last_end
        assert end > start

@pytest.mark.asyncio
async def test_sync_runner_advances_checkpoint_on_success(mock_db, mock_bq):
    """Test that sync runner marks success and advances checkpoint if raw loads succeed."""
    with patch("app.modules.data_pipeline.checkpoint_manager.get_checkpoint_window", new_callable=AsyncMock) as mock_win:
        mock_win.return_value = (
            datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
        )
        with patch("app.modules.data_pipeline.repository.create_pipeline_run", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "run_123"
            with patch("app.modules.data_pipeline.repository.update_pipeline_run_running", new_callable=AsyncMock):
                with patch("app.modules.data_pipeline.sync_runner.run_with_retry", new_callable=AsyncMock) as mock_retry:
                    mock_retry.return_value = (True, 1, "")
                    with patch("app.modules.data_pipeline.repository.mark_pipeline_run_succeeded", new_callable=AsyncMock) as mock_success:
                        
                        run_id = await sync_runner.run_incremental_sync(mock_db, mock_bq, store_id="store_1")
                        
                        assert run_id == "run_123"
                        mock_success.assert_called_once()

@pytest.mark.asyncio
async def test_repair_runner_parses_batch_ref_and_overrides_checkpoint(mock_db, mock_bq):
    """Test that repair_runner extracts batch_ref bounds and passes them to sync_runner."""
    from app.modules.data_pipeline import repair_runner
    
    mock_failures = [{
        "failure_id": "fail_123",
        "pipeline_run_id": "run_failed",
        "batch_ref": "2025-01-01T00:00:00+00:00/2025-01-02T00:00:00+00:00"
    }]
    
    with patch("app.modules.data_pipeline.repository.list_pipeline_failures", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_failures
        with patch("app.modules.data_pipeline.repository.mark_failure_reprocessing", new_callable=AsyncMock):
            with patch("app.modules.data_pipeline.sync_runner.run_incremental_sync", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = "new_run_123"
                with patch("app.modules.data_pipeline.repository.get_pipeline_run", new_callable=AsyncMock) as mock_get_run:
                    mock_get_run.return_value = {"status": "SUCCEEDED", "checkpoint_start": datetime(2025, 1, 1, tzinfo=timezone.utc), "checkpoint_end": datetime(2025, 1, 2, tzinfo=timezone.utc)}
                    with patch("app.modules.data_pipeline.transform_runner.run_mart_refresh", new_callable=AsyncMock):
                        with patch("app.modules.data_pipeline.repository.mark_failure_recovered", new_callable=AsyncMock):
                            
                            res = await repair_runner.run_repair(mock_db, mock_bq, store_id="store_1")
                            
                            assert res["recovered"] == 1
                            assert res["failed"] == 0
                            
                            # Verify the checkpoint override was passed properly
                            mock_sync.assert_called_once()
                            _, kwargs = mock_sync.call_args
                            assert "checkpoint_override" in kwargs
                            start, end = kwargs["checkpoint_override"]
                            assert start == datetime(2025, 1, 1, tzinfo=timezone.utc)
                            assert end == datetime(2025, 1, 2, tzinfo=timezone.utc)
