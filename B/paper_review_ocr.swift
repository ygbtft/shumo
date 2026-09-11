// Local OCR for user-provided screenshots. Never edits original images.
import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count == 3 else {
    fatalError("Usage: paper_review_ocr.swift input-directory output-directory")
}
let source = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let destination = URL(fileURLWithPath: CommandLine.arguments[2]).standardizedFileURL
let allowed = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("B").standardizedFileURL.path + "/"
guard destination.path.hasPrefix(allowed) else { fatalError("Output must be inside B/") }
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
let files = try FileManager.default.contentsOfDirectory(at: source, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension.lowercased() == "png" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
for file in files {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    request.usesCPUOnly = true
    let handler = VNImageRequestHandler(url: file, options: [:])
    try handler.perform([request])
    let rows = (request.results ?? []).compactMap { observation -> [String: Any]? in
        guard let top = observation.topCandidates(1).first else { return nil }
        let b = observation.boundingBox
        return ["text": top.string, "confidence": top.confidence, "box": [b.minX, b.minY, b.width, b.height]]
    }
    let name = file.deletingPathExtension().lastPathComponent
    let bytes = try JSONSerialization.data(withJSONObject: rows, options: [.prettyPrinted, .sortedKeys])
    try bytes.write(to: destination.appendingPathComponent(name + ".json"))
    let plain = rows.compactMap { $0["text"] as? String }.joined(separator: "\n")
    try plain.write(to: destination.appendingPathComponent(name + ".txt"), atomically: true, encoding: .utf8)
    print("OCR \(file.lastPathComponent): \(rows.count) text boxes")
}
