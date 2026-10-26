import Foundation
import Vision
import ImageIO

// Local face detection only. No network, face recognition, or model downloads.
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNDetectFaceRectanglesRequest()
try VNImageRequestHandler(url: url).perform([request])
let boxes = (request.results ?? []).map { face in
    ["x": face.boundingBox.minX, "y": face.boundingBox.minY,
     "width": face.boundingBox.width, "height": face.boundingBox.height]
}
let data = try JSONSerialization.data(withJSONObject: boxes)
FileHandle.standardOutput.write(data)
