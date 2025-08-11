import cadquery as cq
import math

def cycloid_gear(
    module: float,
    teeth: int,
    thickness: float,
    pressure_angle: float = 20.0
) -> cq.Solid:
    """
    生成摆线齿轮
    :param module: 齿轮模数
    :param teeth: 齿轮齿数
    :param thickness: 齿轮厚度
    :param pressure_angle: 压力角，默认为20度
    :return: 摆线齿轮的CadQuery模型
    """
    # 计算齿轮的基本参数
    pitch_diameter = module * teeth
    addendum = module
    dedendum = 1.25 * module
    outer_diameter = pitch_diameter + 2 * addendum
    root_diameter = pitch_diameter - 2 * dedendum

    # 生成摆线齿轮的轮廓
    gear = (
        cq.Workplane("XY")
        .circle(outer_diameter / 2)
        .circle(root_diameter / 2)
        .extrude(thickness)
    )

    return gear

# 生成摆线齿轮
gear = cycloid_gear(module=2, teeth=20, thickness=10)

# 导出为STEP文件
gear.export("C:\\Users\\dell\\Projects\\cadquery_test\\cadquery_test\\mcp\\mcp_out\\1_b0734829-6d9e-43e7-950f-b717c22ed07e_145_1754619240_619.step")