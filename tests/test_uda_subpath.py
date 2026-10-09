"""UDA and LAN smoke tests without invoking transcription."""
import io
from tests.test_app import make_app

def test_uda_prefix_and_upload(tmp_path):
    app=make_app(tmp_path)
    client=app.test_client()
    assert '<base href="/">' in client.get("/").get_data(as_text=True)
    headers={"X-Forwarded-Prefix":"/apps/whisperdesk","X-Forwarded-Host":"tanyaanne.ddns.net","X-Forwarded-Proto":"https"}
    page=client.get("/",headers=headers)
    assert page.status_code==200
    assert '<base href="/apps/whisperdesk/">' in page.get_data(as_text=True)
    assert 'action="/apps/whisperdesk/upload"' in page.get_data(as_text=True)
    upload=client.post("/upload",headers={**headers,"X-Requested-With":"XMLHttpRequest"},data={"file":(io.BytesIO(b"sample"),"meeting.mp3")},content_type="multipart/form-data")
    assert upload.status_code==201
    assert upload.get_json()["redirect_url"].startswith("/apps/whisperdesk/")
