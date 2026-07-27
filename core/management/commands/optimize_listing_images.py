from PIL import UnidentifiedImageError

from django.core.management.base import BaseCommand

from core.image_utils import resize_for_web
from core.models import ListingImage
from core.supabase_storage import download_listing_image, is_storage_configured, upload_listing_image


class Command(BaseCommand):
    help = (
        'Re-encode existing listing images to a web-friendly size/quality '
        '(downloads each from Supabase Storage, resizes, uploads back to the '
        'same object path). Use --dry-run to see savings without writing anything.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Report savings without uploading.")

    def handle(self, *args, **options):
        if not is_storage_configured():
            self.stderr.write(self.style.ERROR('Supabase Storage is not configured.'))
            return

        dry_run = options['dry_run']
        images = list(ListingImage.objects.select_related('listing').all())
        total_before = 0
        total_after = 0
        skipped = 0

        for img in images:
            data = download_listing_image(img.image_path)
            if data is None:
                self.stderr.write(f'Could not download {img.image_path}, skipping.')
                skipped += 1
                continue

            before = len(data)
            try:
                resized, content_type = resize_for_web(data)
            except UnidentifiedImageError:
                self.stderr.write(f'Not a readable image, skipping: {img.image_path}')
                skipped += 1
                continue

            after = len(resized)
            total_before += before
            total_after += after
            pct = (1 - after / before) * 100 if before else 0
            self.stdout.write(
                f'{img.listing.title[:40]:40} {img.image_path:40} '
                f'{before / 1024:>7.0f} KB -> {after / 1024:>7.0f} KB ({pct:.0f}% smaller)'
            )

            if not dry_run:
                upload_listing_image(file_bytes=resized, object_path=img.image_path, content_type=content_type)

        self.stdout.write(self.style.SUCCESS(
            f'{"Would process" if dry_run else "Processed"} {len(images) - skipped} of {len(images)} images. '
            f'{total_before / 1024 / 1024:.1f} MB -> {total_after / 1024 / 1024:.1f} MB.'
        ))
