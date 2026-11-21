#ifdef EMSCRIPTEN

#include "js-interface.hpp"
#include "importer-step.hpp"
#include "importer-iges.hpp"
#include "importer-brep.hpp"
#include <emscripten/bind.h>
#include <cstdint>

static emscripten::val CreateFloat32Array (const std::vector<float>& values)
{
    emscripten::val Float32Array = emscripten::val::global ("Float32Array");
    if (values.empty ()) {
        return Float32Array.new_ (0);
    }

    emscripten::val memoryView = emscripten::val (emscripten::typed_memory_view (values.size (), values.data ()));
    return Float32Array.new_ (memoryView);
}

static emscripten::val CreateUint32Array (const std::vector<std::uint32_t>& values)
{
    emscripten::val Uint32Array = emscripten::val::global ("Uint32Array");
    if (values.empty ()) {
        return Uint32Array.new_ (0);
    }

    emscripten::val memoryView = emscripten::val (emscripten::typed_memory_view (values.size (), values.data ()));
    return Uint32Array.new_ (memoryView);
}

static std::vector<std::uint8_t> CopyUint8Array (const emscripten::val& buffer)
{
    std::size_t bufferLength = 0;
    emscripten::val byteLength = buffer["byteLength"];
    if (!byteLength.isUndefined ()) {
        bufferLength = byteLength.as<std::size_t> ();
    } else {
        bufferLength = buffer["length"].as<std::size_t> ();
    }

    std::vector<std::uint8_t> bufferArr (bufferLength);
    if (bufferArr.empty ()) {
        return bufferArr;
    }

    emscripten::val memoryView = emscripten::val (emscripten::typed_memory_view (bufferArr.size (), bufferArr.data ()));
    memoryView.call<void> ("set", buffer);
    return bufferArr;
}

static emscripten::val CreateColorArray (const Color& color)
{
    emscripten::val colorArr (emscripten::val::array ());
    colorArr.set (0, color.r);
    colorArr.set (1, color.g);
    colorArr.set (2, color.b);
    return colorArr;
}

static bool ColorsEqual (const Color& a, const Color& b)
{
    return a.r == b.r && a.g == b.g && a.b == b.b;
}

class MeshBounds
{
public:
    MeshBounds () :
        mHasValue (false),
        mMin {0.0f, 0.0f, 0.0f},
        mMax {0.0f, 0.0f, 0.0f}
    {

    }

    void Add (float x, float y, float z)
    {
        float values[3] = {x, y, z};
        if (!mHasValue) {
            for (int axis = 0; axis < 3; axis++) {
                mMin[axis] = values[axis];
                mMax[axis] = values[axis];
            }
            mHasValue = true;
            return;
        }

        for (int axis = 0; axis < 3; axis++) {
            if (values[axis] < mMin[axis]) {
                mMin[axis] = values[axis];
            }
            if (values[axis] > mMax[axis]) {
                mMax[axis] = values[axis];
            }
        }
    }

    bool HasValue () const
    {
        return mHasValue;
    }

    float Min (int axis) const
    {
        return mMin[axis];
    }

    float Max (int axis) const
    {
        return mMax[axis];
    }

private:
    bool mHasValue;
    float mMin[3];
    float mMax[3];
};

static emscripten::val CreateVector3Array (float x, float y, float z)
{
    emscripten::val values (emscripten::val::array ());
    values.set (0, x);
    values.set (1, y);
    values.set (2, z);
    return values;
}

static emscripten::val CreateBoundsObject (const MeshBounds& bounds)
{
    emscripten::val boundsObj (emscripten::val::object ());
    boundsObj.set ("min", CreateVector3Array (bounds.Min (0), bounds.Min (1), bounds.Min (2)));
    boundsObj.set ("max", CreateVector3Array (bounds.Max (0), bounds.Max (1), bounds.Max (2)));
    boundsObj.set ("size", CreateVector3Array (
        bounds.Max (0) - bounds.Min (0),
        bounds.Max (1) - bounds.Min (1),
        bounds.Max (2) - bounds.Min (2)
    ));
    return boundsObj;
}

class BrepFaceRun
{
public:
    BrepFaceRun (int first, int last, const Color& color) :
        first (first),
        last (last),
        hasColor (true),
        color (color)
    {

    }

    BrepFaceRun (int first, int last) :
        first (first),
        last (last),
        hasColor (false),
        color ()
    {

    }

    bool CanExtend (int nextFirst, bool nextHasColor, const Color& nextColor) const
    {
        if (last + 1 != nextFirst || hasColor != nextHasColor) {
            return false;
        }
        return !hasColor || ColorsEqual (color, nextColor);
    }

    int first;
    int last;
    bool hasColor;
    Color color;
};

class HierarchyWriter
{
public:
    HierarchyWriter (emscripten::val& meshesArr, const ImportParams& params) :
        mMeshesArr (meshesArr),
        mMeshCount (0),
        mParams (params)
    {
    }

    void WriteNode (const NodePtr& node, emscripten::val& nodeObj)
    {
        nodeObj.set ("name", node->GetName ());

        emscripten::val nodeMeshesArr (emscripten::val::array ());
        WriteMeshes (node, nodeMeshesArr);
        nodeObj.set ("meshes", nodeMeshesArr);

        std::vector<NodePtr> children = node->GetChildren ();
        emscripten::val childrenArr (emscripten::val::array ());
        for (int childIndex = 0; childIndex < children.size (); childIndex++) {
            const NodePtr& child = children[childIndex];
            emscripten::val childNodeObj (emscripten::val::object ());
            WriteNode (child, childNodeObj);
            childrenArr.set (childIndex, childNodeObj);
        }
        nodeObj.set ("children", childrenArr);
    }

private:
    void WriteMeshes (const NodePtr& node, emscripten::val& nodeMeshesArr)
    {
        if (!node->IsMeshNode ()) {
            return;
        }

        int nodeMeshCount = 0;
        node->EnumerateMeshes ([&](const Mesh& mesh) {
            emscripten::val meshObj (emscripten::val::object ());
            meshObj.set ("name", mesh.GetName ());

            int vertexCount = 0;
            int normalCount = 0;
            int triangleCount = 0;
            int brepFaceCount = 0;
            int coloredBrepFaceCount = 0;
            MeshBounds bounds;

            std::vector<float> positionArr;
            std::vector<float> normalArr;
            std::vector<std::uint32_t> indexArr;
            std::vector<BrepFaceRun> brepFaceRuns;
            emscripten::val brepFaceArr (emscripten::val::array ());

            mesh.EnumerateFaces ([&](const Face& face) {
                int triangleOffset = triangleCount;
                int vertexOffset = vertexCount;
                face.EnumerateVertices ([&](double x, double y, double z) {
                    float xf = static_cast<float> (x);
                    float yf = static_cast<float> (y);
                    float zf = static_cast<float> (z);
                    positionArr.push_back (xf);
                    positionArr.push_back (yf);
                    positionArr.push_back (zf);
                    bounds.Add (xf, yf, zf);
                    vertexCount += 1;
                });
                face.EnumerateNormals ([&](double x, double y, double z) {
                    normalArr.push_back (static_cast<float> (x));
                    normalArr.push_back (static_cast<float> (y));
                    normalArr.push_back (static_cast<float> (z));
                    normalCount += 1;
                });
                face.EnumerateTriangles ([&](int v0, int v1, int v2) {
                    indexArr.push_back (static_cast<std::uint32_t> (vertexOffset + v0));
                    indexArr.push_back (static_cast<std::uint32_t> (vertexOffset + v1));
                    indexArr.push_back (static_cast<std::uint32_t> (vertexOffset + v2));
                    triangleCount += 1;
                });
                Color faceColor;
                bool hasFaceColor = face.GetColor (faceColor);
                if (hasFaceColor) {
                    coloredBrepFaceCount += 1;
                }
                if (mParams.includeBrepFaces) {
                    emscripten::val brepFaceObj (emscripten::val::object ());
                    brepFaceObj.set ("first", triangleOffset);
                    brepFaceObj.set ("last", triangleCount - 1);
                    if (hasFaceColor) {
                        brepFaceObj.set ("color", CreateColorArray (faceColor));
                    } else {
                        brepFaceObj.set ("color", emscripten::val::null ());
                    }
                    brepFaceArr.set (brepFaceCount, brepFaceObj);
                }
                brepFaceCount += 1;

                int triangleLast = triangleCount - 1;
                if (triangleLast >= triangleOffset) {
                    if (!brepFaceRuns.empty () && brepFaceRuns.back ().CanExtend (triangleOffset, hasFaceColor, faceColor)) {
                        brepFaceRuns.back ().last = triangleLast;
                    } else if (hasFaceColor) {
                        brepFaceRuns.push_back (BrepFaceRun (triangleOffset, triangleLast, faceColor));
                    } else {
                        brepFaceRuns.push_back (BrepFaceRun (triangleOffset, triangleLast));
                    }
                }
            });

            emscripten::val attributesObj (emscripten::val::object ());

            emscripten::val positionObj (emscripten::val::object ());
            positionObj.set ("array", CreateFloat32Array (positionArr));
            attributesObj.set ("position", positionObj);

            if (vertexCount == normalCount) {
                emscripten::val normalObj (emscripten::val::object ());
                normalObj.set ("array", CreateFloat32Array (normalArr));
                attributesObj.set ("normal", normalObj);
            }

            emscripten::val indexObj (emscripten::val::object ());
            indexObj.set ("array", CreateUint32Array (indexArr));

            meshObj.set ("attributes", attributesObj);
            meshObj.set ("index", indexObj);
            meshObj.set ("vertex_count", vertexCount);
            meshObj.set ("triangle_count", triangleCount);
            if (bounds.HasValue ()) {
                meshObj.set ("bounds", CreateBoundsObject (bounds));
            }

            Color meshColor;
            if (mesh.GetColor (meshColor)) {
                meshObj.set ("color", CreateColorArray (meshColor));
            }

            meshObj.set ("brep_face_count", brepFaceCount);
            meshObj.set ("colored_brep_face_count", coloredBrepFaceCount);
            if (mParams.includeBrepFaces) {
                meshObj.set ("brep_faces", brepFaceArr);
            }

            emscripten::val brepFaceRunArr (emscripten::val::array ());
            for (int runIndex = 0; runIndex < brepFaceRuns.size (); runIndex++) {
                const BrepFaceRun& run = brepFaceRuns[runIndex];
                emscripten::val runObj (emscripten::val::object ());
                runObj.set ("first", run.first);
                runObj.set ("last", run.last);
                if (run.hasColor) {
                    runObj.set ("color", CreateColorArray (run.color));
                } else {
                    runObj.set ("color", emscripten::val::null ());
                }
                brepFaceRunArr.set (runIndex, runObj);
            }
            meshObj.set ("brep_face_runs", brepFaceRunArr);

            mMeshesArr.set (mMeshCount, meshObj);
            nodeMeshesArr.set (nodeMeshCount, mMeshCount);
            mMeshCount += 1;
            nodeMeshCount += 1;
        });
    }

    emscripten::val& mMeshesArr;
    int mMeshCount;
    const ImportParams& mParams;
};

static void EnumerateNodeMeshes (const NodePtr& node, const std::function<void (const Mesh&)>& onMesh)
{
    if (node->IsMeshNode ()) {
        node->EnumerateMeshes (onMesh);
    }
    std::vector<NodePtr> children = node->GetChildren ();
    for (const NodePtr& child : children) {
        EnumerateNodeMeshes (child, onMesh);
    }
}

static emscripten::val ImportFile (ImporterPtr importer, const emscripten::val& buffer, const ImportParams& params)
{
    emscripten::val resultObj (emscripten::val::object ());

    std::vector<std::uint8_t> bufferArr = CopyUint8Array (buffer);
    Importer::Result importResult = importer->LoadFile (bufferArr, params);
    resultObj.set ("success", importResult == Importer::Result::Success);
    if (importResult != Importer::Result::Success) {
        return resultObj;
    }

    int meshIndex = 0;
    emscripten::val rootNodeObj (emscripten::val::object ());
    emscripten::val meshesArr (emscripten::val::array ());
    NodePtr rootNode = importer->GetRootNode ();

    HierarchyWriter hierarchyWriter (meshesArr, params);
    hierarchyWriter.WriteNode (rootNode, rootNodeObj);

    resultObj.set ("root", rootNodeObj);
    resultObj.set ("meshes", meshesArr);
    return resultObj;
}

static ImportParams GetImportParams (const emscripten::val& paramsVal)
{
    ImportParams params;
    if (paramsVal.isUndefined () || paramsVal.isNull ()) {
        return params;
    }

    if (paramsVal.hasOwnProperty ("linearUnit")) {
        emscripten::val linearUnit = paramsVal["linearUnit"];
        std::string linearUnitStr = linearUnit.as<std::string> ();
        if (linearUnitStr == "millimeter") {
            params.linearUnit = ImportParams::LinearUnit::Millimeter;
        } else if (linearUnitStr == "centimeter") {
            params.linearUnit = ImportParams::LinearUnit::Centimeter;
        } else if (linearUnitStr == "meter") {
            params.linearUnit = ImportParams::LinearUnit::Meter;
        } else if (linearUnitStr == "inch") {
            params.linearUnit = ImportParams::LinearUnit::Inch;
        } else if (linearUnitStr == "foot") {
            params.linearUnit = ImportParams::LinearUnit::Foot;
        }
    }

    if (paramsVal.hasOwnProperty ("linearDeflectionType")) {
        emscripten::val linearDeflectionType = paramsVal["linearDeflectionType"];
        std::string linearDeflectionTypeStr = linearDeflectionType.as<std::string> ();
        if (linearDeflectionTypeStr == "bounding_box_ratio") {
            params.linearDeflectionType = ImportParams::LinearDeflectionType::BoundingBoxRatio;
        } else if (linearDeflectionTypeStr == "absolute_value") {
            params.linearDeflectionType = ImportParams::LinearDeflectionType::AbsoluteValue;
        }
    }

    if (paramsVal.hasOwnProperty ("linearDeflection")) {
        emscripten::val linearDeflection = paramsVal["linearDeflection"];
        params.linearDeflection = linearDeflection.as<double> ();
    }

    if (paramsVal.hasOwnProperty ("angularDeflection")) {
        emscripten::val angularDeflection = paramsVal["angularDeflection"];
        params.angularDeflection = angularDeflection.as<double> ();
    }

    if (paramsVal.hasOwnProperty ("includeBrepFaces")) {
        emscripten::val includeBrepFaces = paramsVal["includeBrepFaces"];
        params.includeBrepFaces = includeBrepFaces.as<bool> ();
    }

    return params;
}

emscripten::val ReadStepFile (const emscripten::val& buffer, const emscripten::val& params)
{
    ImporterPtr importer = std::make_shared<ImporterStep> ();
    ImportParams importParams = GetImportParams (params);
    return ImportFile (importer, buffer, importParams);
}

emscripten::val ReadIgesFile (const emscripten::val& buffer, const emscripten::val& params)
{
    ImporterPtr importer = std::make_shared<ImporterIges> ();
    ImportParams importParams = GetImportParams (params);
    return ImportFile (importer, buffer, importParams);
}

emscripten::val ReadBrepFile (const emscripten::val& buffer, const emscripten::val& params)
{
    ImporterPtr importer = std::make_shared<ImporterBrep> ();
    ImportParams importParams = GetImportParams (params);
    return ImportFile (importer, buffer, importParams);
}

emscripten::val ReadFile (const std::string& format, const emscripten::val& buffer, const emscripten::val& params)
{
    if (format == "step") {
        return ReadStepFile (buffer, params);
    } else if (format == "iges") {
        return ReadIgesFile (buffer, params);
    } else if (format == "brep") {
        return ReadBrepFile (buffer, params);
    } else {
        emscripten::val resultObj (emscripten::val::object ());
        resultObj.set ("success", false);
        return resultObj;
    }
}

EMSCRIPTEN_BINDINGS (occtimportjs)
{
    emscripten::function<emscripten::val, const std::string&, const emscripten::val&, const emscripten::val&> ("ReadFile", &ReadFile);

    emscripten::function<emscripten::val, const emscripten::val&, const emscripten::val&> ("ReadStepFile", &ReadStepFile);
    emscripten::function<emscripten::val, const emscripten::val&, const emscripten::val&> ("ReadIgesFile", &ReadIgesFile);
    emscripten::function<emscripten::val, const emscripten::val&, const emscripten::val&> ("ReadBrepFile", &ReadBrepFile);
}

#endif
