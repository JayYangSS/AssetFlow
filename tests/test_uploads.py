from assetflow.uploads import InvalidUploadError, store_upload


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + (b"0" * 64)


def test_store_upload_saves_image_and_hash(settings, session) -> None:
    upload = store_upload(
        session=session,
        settings=settings,
        broker="htsc_global",
        source="ios_shortcut",
        filename="trade.png",
        content_type="image/png",
        data=PNG_BYTES,
    )

    assert upload.id is not None
    assert upload.status == "stored"
    assert upload.content_hash
    assert settings.upload_dir.joinpath(upload.content_hash + ".png").exists()


def test_store_upload_marks_duplicate(settings, session) -> None:
    first = store_upload(session, settings, "htsc_global", "ios_shortcut", "a.png", "image/png", PNG_BYTES)
    second = store_upload(session, settings, "htsc_global", "ios_shortcut", "b.png", "image/png", PNG_BYTES)

    assert second.status == "duplicate"
    assert second.duplicate_of_upload_id == first.id


def test_store_upload_rejects_non_image(settings, session) -> None:
    try:
        store_upload(session, settings, "htsc_global", "ios_shortcut", "note.txt", "text/plain", b"hello")
    except InvalidUploadError as exc:
        assert "Unsupported image type" in str(exc)
    else:
        raise AssertionError("Expected InvalidUploadError")
