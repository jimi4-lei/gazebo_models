#!/usr/bin/env python3
"""用拆分后的彩色 mesh 替换 dog_robocon.xml 里的单一视觉网格。"""
import re
import sys

SPLIT = '/home/uwvwko/桌面/rc/gazebo_models/robocon_ground/mujoco/split/'
XML = sys.argv[1] if len(sys.argv) > 1 else '/home/uwvwko/桌面/rc/gazebo_models/robocon_mujoco/dog_robocon.xml'

snippet = open(SPLIT + 'robocon_geoms.xml').read()
m = re.search(r'<!-- 放入 <asset> -->\n(.*?)\n\n<!-- 放入 worldbody.*?-->\n(.*)', snippet, re.S)
assets = m.group(1).strip()
geoms = '\n'.join('  ' + l.strip() for l in m.group(2).strip().splitlines())

xml = open(XML).read()
xml, n1 = re.subn(
    r'<!-- ROBOCON 场地彩色网格 \(由 DAE 转换\) -->\n<mesh name="robocon_visual" file="robocon_ground\.obj"/>',
    '<!-- ROBOCON 场地彩色网格 (按材质拆分, MuJoCo 不支持 MTL/顶点色) -->\n' + assets,
    xml)
xml, n2 = re.subn(
    r'  <!-- 视觉：整个场地的彩色网格（红蓝半场、起点等），不参与碰撞 -->\n  <geom name="robocon_visual_field"[^/]*/>\n',
    '  <!-- 视觉：整个场地的彩色网格（红蓝半场、起点等），不参与碰撞 -->\n' + geoms + '\n',
    xml)
open(XML, 'w').write(xml)
print('asset replaced:', n1, 'geom replaced:', n2)
print('mesh count:', xml.count('<mesh name="robocon_'))
print('visual geom count:', len(re.findall(r'name="robocon_\d+_v"', xml)))
