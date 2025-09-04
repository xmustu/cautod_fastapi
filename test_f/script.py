import cadquery as cq

# 参数列表
cube_length = 10
cube_width = 10
cube_height = 10
cube_center_x = 0
cube_center_y = 0
cube_center_z = 0
cube_fillet_radius = 2  # 示例：设置圆角半径为2
cube_chamfer_distance = 0
cube_hole_diameter = 4  # 示例：设置孔直径为4
cube_hole_axis = "Z"

# 计算立方体起始点（左下角）
x0 = cube_center_x - cube_length / 2
y0 = cube_center_y - cube_width / 2
z0 = cube_center_z - cube_height / 2

# 创建基础立方体
result = cq.Workplane("XY").moveTo(x0, y0).rect(cube_length, cube_width).extrude(cube_height)

# 倒圆角
if cube_fillet_radius > 0:
    result = result.edges().fillet(cube_fillet_radius)

# 倒斜角
if cube_chamfer_distance > 0:
    result = result.edges().chamfer(cube_chamfer_distance)

# 中心孔
if cube_hole_diameter > 0:
    hole_radius = cube_hole_diameter / 2
    if cube_hole_axis.upper() == "X":
        result = result.faces(">X").workplane(centerOption="CenterOfMass").circle(hole_radius).cutThruAll()
    elif cube_hole_axis.upper() == "Y":
        result = result.faces(">Y").workplane(centerOption="CenterOfMass").circle(hole_radius).cutThruAll()
    else:  # Z
        result = result.faces(">Z").workplane(centerOption="CenterOfMass").circle(hole_radius).cutThruAll()

# --------------------------
# 2. 文本标注核心配置（关键优化）
# --------------------------
text_config = {
    "height": 1.2,    # 文本高度（根据模型尺寸调整，避免过大）
    "thickness": 0.3, # 文本厚度（轻量化，避免占用过多空间）
    "offset": 1.5,    # 文本与模型的间距（大于文本高度的1/2，避免贴紧）
    "spacing": 2.0    # 不同文本之间的间距（大于文本高度，避免重叠）
}

# --------------------------
# 3. 按特征绑定标注（核心优化：每个标注对应独立空间）
# --------------------------
def add_text_label(workplane, text, x, y, z=0):
    """封装文本标注函数：统一风格，避免重复代码"""
    return workplane.moveTo(x, y) \
                    .text(text, text_config["height"], text_config["thickness"]) \
                    .translate((0, 0, z))  # Z方向分层（可选，用于不同平面标注）

# 3.1 长度标注（X方向特征：绑定立方体右侧边缘）
length_text = f"长度: {cube_length}"
# 位置：立方体右侧 + 偏移量（X方向超出模型，Y方向居中）
length_x = cube_center_x + cube_length/2 + text_config["offset"]
length_y = cube_center_y
length_label = add_text_label(
    cq.Workplane("XY"),  # 长度在XY平面展示
    length_text,
    length_x,
    length_y
)
result = result.union(length_label)

# 3.2 宽度标注（Y方向特征：绑定立方体前方边缘，与长度标注Y方向错开）
width_text = f"宽度: {cube_width}"
# 位置：立方体前方 + 偏移量 + 间距（Y方向超出模型，X方向错开长度标注）
width_x = cube_center_x + text_config["spacing"]  # X方向错开
width_y = cube_center_y + cube_width/2 + text_config["offset"]
width_label = add_text_label(
    cq.Workplane("XY"),  # 宽度在XY平面展示
    width_text,
    width_x,
    width_y
)
result = result.union(width_label)

# # 3.3 高度标注（Z方向特征：绑定立方体上方边缘，切换到XZ平面避免重叠）
# height_text = f"高度: {cube_height}"
# # 位置：立方体上方 + 偏移量（Z方向超出模型，X方向左移错开）
# height_x = cube_center_x - cube_length/2 - text_config["offset"]  # X方向左移
# height_z = cube_center_z + cube_height/2 + text_config["offset"]
# height_label = add_text_label(
#     cq.Workplane("XZ"),  # 高度在XZ平面展示（与XY平面垂直，空间不重叠）
#     height_text,
#     height_x,
#     height_z  # XZ平面中，第二个参数是Z轴坐标
# )
# result = result.union(height_label)

# 3.4 圆角标注（绑定立方体左下角圆角，与其他标注间距拉开）
if cube_fillet_radius > 0:
    fillet_text = f"圆角半径: {cube_fillet_radius}"
    # 位置：立方体左下角外侧 + 双偏移（远离其他标注）
    fillet_x = cube_center_x - cube_length/2 - text_config["offset"] - text_config["spacing"]
    fillet_y = cube_center_y - cube_width/2 - text_config["offset"]
    fillet_label = add_text_label(
        cq.Workplane("XY"),
        fillet_text,
        fillet_x,
        fillet_y
    )
    result = result.union(fillet_label)

# 3.5 孔直径标注（绑定孔的正上方，Z方向分层）
if cube_hole_diameter > 0:
    hole_text = f"孔直径: {cube_hole_diameter}"
    # 位置：孔中心正上方（Z方向超出模型，避免与高度标注重叠）
    hole_x = cube_center_x
    hole_y = cube_center_y
    hole_z = cube_center_z + cube_height/2 + text_config["offset"] + text_config["spacing"]  # Z方向分层
    hole_label = add_text_label(
        cq.Workplane("XY"),
        hole_text,
        hole_x,
        hole_y,
        hole_z  # Z方向抬高，与高度标注（XZ平面）不重叠
    )
    result = result.union(hole_label)

# 导出模型和截图
result.export(r'.\model_with_labels.step')
cq.exporters.export(result, r'.\model.stl', 'STL')
from cadquery.vis import show
show(result, title='带参数标注的模型', roll=10, elevation=-65, 
     screenshot=r'.\model_with_labels.png', 
     interact=False)