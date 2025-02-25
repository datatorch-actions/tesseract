<h1 align="center">
  Tesseract OCR
</h1>

<h4 align="center">Use Tesseract OCR for optical character recognition</h4>

## Quick Start

```yaml
name: Tesseract OCR

triggers:
  # Adds a button to the annotator.
  annotatorButton:
    name: "Tesseract Whole File"
    icon: brain
    flow: whole-file

jobs:
  predict:
    # Properties about the trigger event can be accessed at 'event' property
    steps:
      - name: Download File
        action: datatorch/download-file@v1
        inputs:
          # Get the file id for the event that triggered this.
          fileId: ${{ event.fileId }}
          name: ${{ event.fileName }}

      - name: Predict Segmentation
        action: datatorch/tesseract@latest
        inputs:
          # Download file path from the previous action.
          imagePath: ${{ variable.path }}

          # Get the file id from action input
          fileId: ${{ event.fileId }}
         
```

> **NOTE:** Running Segformer for the first time will take serval minutes to
> complete as it needs to download the Segformer docker image. Do not exit out of
> your agent unless it specifically throws an error.

## Action

### Inputs

| Name           |  Type  |         Default          | Description                                                                                                                                                                            |
| -------------- | :----: | :----------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `imagePath`    | string |        _required_        | Absolute path to image. This path must be in the agent directory.                                                                                                                      |
| `points`       | array  |        _required_        | 4 points marking the most left, right, bottom and top points of the shape.                                                                                                             |
| `url`          | string | `http://localhost:3445`  | Url for sending requests. A Segformer docker image will be spun up on this port if not found.                                                                                              |
| `image`        | string | `add3000/segformer_server` | Docker image to spin up.                                                                                                                                                               |
| `annotationId` | string |          `null`          | Annotation to insert segmentation into. If not provided the segmentation will not be inserted.                                                                                         |
| `simplify`     | float  |          `1.5`           | Simplification tolerance applied to segmentation before importing. Set to 0 to disable. Disabling can significantly increase pipeline performance, but decrease annotator performance. |

### Outputs

| Name           | Type  | Description                                |
| -------------- | :---: | ------------------------------------------ |
| `segmentation` | array | Segmentation of points predicted by Segformer |
