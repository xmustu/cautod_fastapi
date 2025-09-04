from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
import cadquery as cq
import tempfile
import os
from pathlib import Path

app = FastAPI()

def generate_model():
    # 创建一个简单的CadQuery模型
    box = cq.Workplane("XY").box(10, 10, 10).edges("|Z").fillet(2)
    cylinder = cq.Workplane("XY").circle(3).extrude(12).translate((0, 0, 10))
    model = box.cut(cylinder)
    
    # 导出为STL格式
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as temp_file:
        cq.exporters.export(model, temp_file.name, 'STL')
        temp_file_path = temp_file.name
    
    return r"./model.stl"
    # return temp_file_path

@app.get("/model", response_class=Response)
def get_model():
    file_path = generate_model()
    try:
        with open(file_path, "rb") as f:
            stl_content = f.read()
        return Response(content=stl_content, media_type="application/sla")
    finally:
        pass
        # 确保临时文件被删除
        if os.path.exists(file_path):
           os.unlink(file_path)

@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CadQuery 3D模型展示</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/three@0.132.2/build/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.132.2/examples/js/loaders/STLLoader.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.132.2/examples/js/controls/OrbitControls.js"></script>
    </head>
    <body class="bg-gray-100 min-h-screen">
        <div class="container mx-auto px-4 py-8">
            <h1 class="text-3xl font-bold text-center mb-8 text-gray-800">CadQuery 3D模型网页展示 (FastAPI)</h1>
            
            <div class="bg-white rounded-lg shadow-lg p-6 max-w-4xl mx-auto">
                <div id="model-container" class="w-full h-80 border border-gray-200 rounded-lg overflow-hidden"></div>
                
                <div class="mt-6 flex justify-center">
                    <button id="refresh-model" class="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg transition duration-300 flex items-center">
                        <i class="fa fa-refresh mr-2"></i> 生成新模型
                    </button>
                </div>
            </div>
        </div>
        
        <script>
            // 初始化Three.js场景
            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0xf0f0f0);
            
            // 相机
            const camera = new THREE.PerspectiveCamera(75, 
                document.getElementById('model-container').clientWidth / 
                document.getElementById('model-container').clientHeight, 
                0.1, 1000);
            
            // 渲染器
            const renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(
                document.getElementById('model-container').clientWidth, 
                document.getElementById('model-container').clientHeight
            );
            document.getElementById('model-container').appendChild(renderer.domElement);
            
            // 光源
            const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
            scene.add(ambientLight);
            
            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(10, 10, 10);
            scene.add(directionalLight);
            
            // 控制器
            const controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            
            // 加载STL模型
            function loadModel() {
                const loader = new THREE.STLLoader();
                loader.load(
                    '/model',
                    function (geometry) {
                        // 清除现有模型
                        while(scene.children.length > 3) {
                            scene.remove(scene.children[3]);
                        }
                        
                        const material = new THREE.MeshPhongMaterial({ 
                            color: 0x0070f3, 
                            shininess: 100,
                            side: THREE.DoubleSide
                        });
                        const mesh = new THREE.Mesh(geometry, material);
                        
                        // 计算模型中心并居中
                        geometry.computeBoundingBox();
                        const center = new THREE.Vector3();
                        geometry.boundingBox.getCenter(center);
                        mesh.position.sub(center);
                        
                        // 适当缩放
                        const size = new THREE.Vector3();
                        geometry.boundingBox.getSize(size);
                        const maxDim = Math.max(size.x, size.y, size.z);
                        const scale = 10 / maxDim;
                        mesh.scale.set(scale, scale, scale);
                        
                        scene.add(mesh);
                        
                        // 调整相机位置
                        camera.position.z = 20;
                    },
                    function (xhr) {
                        console.log((xhr.loaded / xhr.total * 100) + '% loaded');
                    },
                    function (error) {
                        console.log('An error happened', error);
                    }
                );
            }
            
            // 窗口大小调整
            window.addEventListener('resize', () => {
                const container = document.getElementById('model-container');
                camera.aspect = container.clientWidth / container.clientHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(container.clientWidth, container.clientHeight);
            });
            
            // 动画循环
            function animate() {
                requestAnimationFrame(animate);
                controls.update();
                renderer.render(scene, camera);
            }
            
            // 刷新模型按钮
            document.getElementById('refresh-model').addEventListener('click', loadModel);
            
            // 初始化
            loadModel();
            animate();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8015, reload=True)