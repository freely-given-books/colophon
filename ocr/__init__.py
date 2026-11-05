"""
OCR of a printed source, and the witnesses it gives.

A scan is kept as a bundle, a folder (ocr-witnesses/<scan-id>/ beside the
book's source, or under work/<book>/):

  source/<scan>.pdf             the scan, untouched (or source/*.png|jpg|jp2
                                page images, in page order)
  pages/NNNNNN.png              each page at 300 dpi, rendered once (bundle.py)
  <engine>/pages/NNNNNN.txt     each engine's reading of each page; Tesseract
                                also .tsv (word boxes, for crops) and .hocr;
                                Kraken also .xml (ALTO) with --alto
  <engine>/full-text.txt        the pages joined, "--- PDF page N ---" between
  manifest.json                 the scan's checksum and each engine's settings

  bundle.py   the bundle: pages, the manifest, the export
  engines.py  Tesseract, Kraken, GLM-OCR (one engine at a time: GPU jobs
              never run side by side)
  collate.py  the light pass: a TCP book's printed text against the witnesses
  crops.py    the printed lines of a candidate, cut from the page, to read

Kraken and GLM-OCR are not colophon dependencies: Kraken is found through
$FGB_KRAKEN (its executable) and $FGB_KRAKEN_MODEL (the recognition model,
e.g. CATMuS-Print fondue large); GLM-OCR through Ollama ($FGB_OLLAMA, default
http://localhost:11434). Tesseract is the one engine every setup has.
"""
