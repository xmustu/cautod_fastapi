import cadquery as cq

def cycloidal_gear(
    outer_radius: float,
    inner_radius: float,
    tooth_count: int,
    gear_height: float
) -> cq.Solid:
    """
    - 零件名称：摆线齿轮
    - 几何特征：生成摆线齿轮的几何形状
    - 典型用途：用于机械传动系统中的齿轮
    """
    # 创建摆线齿轮的外轮廓
    gear = (
        cq.Workplane("XY")
        .circle(outer_radius)
        .extrude(gear_height)
    )
    
    # 创建摆线齿轮的内轮廓
    gear = gear.cut(
        cq.Workplane("XY")
        .circle(inner_radius)
        .extrude(gear_height)
    )
    
    # 创建摆线齿轮的齿
    for i in range(tooth_count):
        angle = 360 / tooth_count * i
        tooth = (
            cq.Workplane("XY")
            .moveTo(outer_radius, 0)
            .lineTo(outer_radius + 5, 0)
            .lineTo(outer_radius + 5, gear_height)
            .lineTo(outer_radius, gear_height)
            .close()
            .extrude(gear_height)
            .rotate((0, 0, 0), (0, 0, 1), angle)
        )
        gear = gear.cut(tooth)
    
    return gear

# 生成摆线齿轮模型
gear = cycloidal_gear(outer_radius=50, inner_radius=30, tooth_count=20, gear_height=10)

# 导出模型为STEP格式
gear.val().exportStep("C:\\Users\\dell\\Projects\\CAutoD\\cautod_fastapi\\files\\mcp_out\\cycloidal_gear.step")