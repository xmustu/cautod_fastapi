import cadquery as cq

block_length = 20
block_width  = 20
block_height = 20

result = (
    cq.Workplane("XY")
    .rect(block_length, block_width)
    .extrude(block_height)
)
result.export(r'shared\23908ada-b763-4f08-84de-b7ccf12041f7\780\model.step')
cq.exporters.export(result, r'shared\23908ada-b763-4f08-84de-b7ccf12041f7\780\model.stl', 'STL')
from cadquery.vis import show
show(result, title='斜视图', roll=10, elevation=-65, screenshot=r'shared\23908ada-b763-4f08-84de-b7ccf12041f7\780\Oblique_View.png', interact=False)