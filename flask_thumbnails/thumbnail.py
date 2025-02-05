# -*- coding: utf-8 -*-
import os
from io import BytesIO

try:
    from PIL import Image, ImageOps
except ImportError as e:
    raise RuntimeError(
        "Get Pillow at https://pypi.python.org/pypi/Pillow "
        'or run command "pip install Pillow".'
    ) from e

from .utils import aspect_to_string, generate_filename, import_from_string, parse_size


class Thumbnail(object):
    def __init__(self, app=None, configure_jinja=True):
        self.app = app
        self._configure_jinja = configure_jinja
        self._default_root_directory = "media"
        self._default_thumbnail_directory = "media"
        self._default_root_url = "/"
        self._default_thumbnail_root_url = "/"
        self._default_format = None
        self._default_storage_backend = (
            "flask_thumbnails.storage_backends.FilesystemStorageBackend"
        )

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        if self.app is None:
            self.app = app
        app.thumbnail_instance = self

        if not hasattr(app, "extensions"):
            app.extensions = {}

        if "thumbnail" in app.extensions:
            raise RuntimeError("Flask-thumbnail extension already initialized")

        app.extensions["thumbnail"] = self

        app.config.setdefault("THUMBNAIL_MEDIA_ROOT", self._default_root_directory)
        app.config.setdefault(
            "THUMBNAIL_MEDIA_THUMBNAIL_ROOT", self._default_thumbnail_directory
        )
        app.config.setdefault("THUMBNAIL_MEDIA_URL", self._default_root_url)
        app.config.setdefault(
            "THUMBNAIL_MEDIA_THUMBNAIL_URL", self._default_thumbnail_root_url
        )
        app.config.setdefault(
            "THUMBNAIL_STORAGE_BACKEND", self._default_storage_backend
        )
        app.config.setdefault("THUMBNAIL_DEFAULT_FORMAT", self._default_format)

        if self._configure_jinja:
            app.jinja_env.filters.update(
                thumbnail=self.get_thumbnail,
            )

    @property
    def root_directory(self):
        path = self.app.config["THUMBNAIL_MEDIA_ROOT"]
        return path if os.path.isabs(path) else os.path.join(self.app.root_path, path)

    @property
    def thumbnail_directory(self):
        path = self.app.config["THUMBNAIL_MEDIA_THUMBNAIL_ROOT"]
        return path if os.path.isabs(path) else os.path.join(self.app.root_path, path)

    @property
    def root_url(self):
        return self.app.config["THUMBNAIL_MEDIA_URL"]

    @property
    def thumbnail_url(self):
        return self.app.config["THUMBNAIL_MEDIA_THUMBNAIL_URL"]

    @property
    def storage_backend(self):
        return self.app.config["THUMBNAIL_STORAGE_BACKEND"]

    def get_storage_backend(self):
        backend_class = import_from_string(self.storage_backend)
        return backend_class(app=self.app)

    def get_thumbnail(self, original, size, **options):
        storage = self.get_storage_backend()
        crop = options.get("crop", "fit")
        background = options.get("background")
        quality = options.get("quality", 90)
        thumbnail_size = parse_size(size)

        original_path, original_filename = os.path.split(original)
        original_filepath = os.path.join(
            self.root_directory, original_path, original_filename
        )

        image = Image.open(BytesIO(storage.read(original_filepath)))
        try:
            image.load()
        except (IOError, OSError):
            self.app.logger.warning("Thumbnail not load image: %s", original_filepath)
            return original_filepath

        # Set format option from original image or settings
        thumbnail_format = self.get_format(image, options)
        thumbnail_filename = generate_filename(
            original_filename,
            aspect_to_string(size),
            crop,
            background,
            quality,
            extension=thumbnail_format,
        )
        thumbnail_filepath = os.path.join(
            self.thumbnail_directory, original_path, thumbnail_filename
        )
        thumbnail_url = os.path.join(
            self.thumbnail_url, original_path, thumbnail_filename
        )

        if storage.exists(thumbnail_filepath):
            return thumbnail_url

        image = self._create_thumbnail(
            image, thumbnail_size, crop, background=background
        )

        _file = BytesIO()
        image.save(_file, format=thumbnail_format, quality=options.get("quality", 90))
        storage.save(thumbnail_filepath, _file.getvalue())

        return thumbnail_url

    def get_format(self, image, options):
        if options.get("format"):
            return options.get("format").lower()

        if self.app.config["THUMBNAIL_DEFAULT_FORMAT"]:
            return self.app.config["THUMBNAIL_DEFAULT_FORMAT"].lower()

        return image.format

    @staticmethod
    def colormode(image, colormode="RGB"):
        if colormode in ["RGB", "RGBA"]:
            if image.mode == "RGBA":
                return image
            if image.mode == "LA":
                return image.convert("RGBA")
            return image.convert(colormode)

        if colormode == "GRAY":
            return image.convert("L")

        return image.convert(colormode)

    @staticmethod
    def background(original_image, color=0xFF):
        size = (max(original_image.size),) * 2
        image = Image.new("L", size, color)
        image.paste(
            original_image,
            tuple(map(lambda x: (x[0] - x[1]) / 2, zip(size, original_image.size))),
        )

        return image

    def _create_thumbnail(self, image, size, crop="fit", background=None):
        if crop == "fit":
            image = ImageOps.fit(image, size, Image.ANTIALIAS)
        else:
            image = image.copy()
            image.thumbnail(size, resample=Image.ANTIALIAS)

        if background is not None:
            image = self.background(image)

        image = self.colormode(image)

        return image
