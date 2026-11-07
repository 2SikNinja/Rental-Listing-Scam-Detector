"use client";

/**
 * Lets the user attach listing photos, with previews and a remove button.
 *
 * The checks here (type, size, count) only give fast, friendly feedback.
 * The API re-checks every file from its actual bytes, because anything
 * done in the browser can be bypassed.
 */

import { useEffect, useMemo, useState, type ChangeEvent } from "react";

export const maxPhotoCount = 10;
export const maxPhotoBytes = 5 * 1024 * 1024;
const acceptedTypes = ["image/jpeg", "image/png", "image/webp"];

interface PhotoPickerProps {
  photos: File[];
  onPhotosChange: (photos: File[]) => void;
}

function formatMegabytes(byteCount: number): string {
  return `${(byteCount / (1024 * 1024)).toFixed(1)} MB`;
}

export default function PhotoPicker({ photos, onPhotosChange }: PhotoPickerProps) {
  const [pickerMessage, setPickerMessage] = useState<string | null>(null);

  // Preview URLs point at the files in browser memory. They are freed
  // when the list changes or the component unmounts, to avoid leaking memory.
  const previewUrls = useMemo(() => photos.map((photo) => URL.createObjectURL(photo)), [photos]);
  useEffect(() => () => previewUrls.forEach((previewUrl) => URL.revokeObjectURL(previewUrl)), [previewUrls]);

  function handleFilesSelected(changeEvent: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(changeEvent.target.files ?? []);
    changeEvent.target.value = ""; // allows picking the same file again after removing it

    const skippedReasons: string[] = [];
    const acceptedFiles = selectedFiles.filter((selectedFile) => {
      if (!acceptedTypes.includes(selectedFile.type)) {
        skippedReasons.push(`${selectedFile.name} is not a JPEG, PNG, or WebP image`);
        return false;
      }
      if (selectedFile.size > maxPhotoBytes) {
        skippedReasons.push(`${selectedFile.name} is larger than ${formatMegabytes(maxPhotoBytes)}`);
        return false;
      }
      return true;
    });

    const combinedPhotos = [...photos, ...acceptedFiles];
    if (combinedPhotos.length > maxPhotoCount) {
      skippedReasons.push(`only the first ${maxPhotoCount} photos were kept`);
    }
    onPhotosChange(combinedPhotos.slice(0, maxPhotoCount));
    setPickerMessage(skippedReasons.length > 0 ? `Skipped: ${skippedReasons.join("; ")}.` : null);
  }

  function removePhoto(photoIndex: number) {
    onPhotosChange(photos.filter((_, index) => index !== photoIndex));
    setPickerMessage(null);
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="mb-2 text-sm font-medium">Listing photos (optional, up to {maxPhotoCount})</p>
        {/* The native file input shows "No file chosen" even when photos are attached,
            so it is visually hidden and a styled label acts as the button instead.
            It stays keyboard-focusable, and the label shows a focus ring. */}
        <input
          id="photos"
          type="file"
          multiple
          accept={acceptedTypes.join(",")}
          onChange={handleFilesSelected}
          disabled={photos.length >= maxPhotoCount}
          className="peer sr-only"
        />
        <label
          htmlFor="photos"
          className="inline-flex cursor-pointer items-center rounded-lg bg-zinc-200 px-4 py-2 text-sm font-medium hover:bg-zinc-300 peer-focus-visible:ring-2 peer-focus-visible:ring-zinc-900 peer-disabled:cursor-not-allowed peer-disabled:opacity-50 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:peer-focus-visible:ring-zinc-100"
        >
          {photos.length === 0 ? "Add photos" : `Add more photos (${photos.length} of ${maxPhotoCount} attached)`}
        </label>
        <p className="mt-1 text-xs text-zinc-500">
          Photos are compared with earlier listings to spot copied pictures. Only a fingerprint of each photo is
          stored, never the photo itself.
        </p>
        {pickerMessage && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{pickerMessage}</p>}
      </div>

      {photos.length > 0 && (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {photos.map((photo, photoIndex) => (
            <li key={`${photo.name}-${photo.size}-${photo.lastModified}`} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview, not a remote image */}
              <img
                src={previewUrls[photoIndex]}
                alt={`Photo ${photoIndex + 1}`}
                className="aspect-square w-full rounded-lg border border-zinc-200 object-cover dark:border-zinc-800"
              />
              <button
                type="button"
                onClick={() => removePhoto(photoIndex)}
                aria-label={`Remove photo ${photoIndex + 1}`}
                className="absolute right-1 top-1 rounded-full bg-black/70 px-2 text-sm leading-6 text-white hover:bg-black"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
