"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ImportPayload(BaseModel):
    """批量导入提交的文件内容（CSV/TSV 文本）与原始文件名。"""

    filename: str | None = None
    content: str = ""


class ImportFailure(BaseModel):
    """逐行校验时未通过的一行：行号、原因与该行原始内容。"""

    line: int
    reason: str
    row: dict[str, Any] = Field(default_factory=dict)


class ImportResult(BaseModel):
    """批量导入结果：成功的立即落库，失败的逐行列出原因；同一文件只记一次。"""

    ok: bool
    message: str
    filename: str | None = None
    duplicate: bool = False
    total: int = 0
    imported: int = 0
    failures: list[ImportFailure] = Field(default_factory=list)
    entries: list[dict[str, Any]] = Field(default_factory=list)



class WindfarmEntry(BaseModel):
    """风电场站明细结构。"""

    field_0: str | None = None  # 场站编码
    field_1: str | None = None  # 场站名称
    field_2: str | None = None  # 所在区域
    field_3: str | None = None  # 装机容量
    field_4: str | None = None  # 并网日期
    field_5: str | None = None  # 运营单位
    field_6: str | None = None  # 海拔高度
    field_7: str | None = None  # 场站状态

class TurbineEntry(BaseModel):
    """风电机组明细结构。"""

    field_0: str | None = None  # 机组编号
    field_1: str | None = None  # 机组机型
    field_2: str | None = None  # 额定功率
    field_3: str | None = None  # 轮毂高度
    field_4: str | None = None  # 所属场站
    field_5: str | None = None  # 投运日期
    field_6: str | None = None  # 累计发电量
    field_7: str | None = None  # 机组状态

class BladeEntry(BaseModel):
    """叶片明细结构。"""

    field_0: str | None = None  # 叶片编号
    field_1: str | None = None  # 所属机组
    field_2: str | None = None  # 叶片长度
    field_3: str | None = None  # 制造厂商
    field_4: str | None = None  # 上次检查日
    field_5: str | None = None  # 裂纹数量
    field_6: str | None = None  # 雷击次数
    field_7: str | None = None  # 叶片状态

class GearboxEntry(BaseModel):
    """齿轮箱明细结构。"""

    field_0: str | None = None  # 齿轮箱编号
    field_1: str | None = None  # 所属机组
    field_2: str | None = None  # 油温上限
    field_3: str | None = None  # 振动值
    field_4: str | None = None  # 上次换油日
    field_5: str | None = None  # 下次换油日
    field_6: str | None = None  # 油品型号
    field_7: str | None = None  # 齿轮箱状态

class GeneratorEntry(BaseModel):
    """发电机明细结构。"""

    field_0: str | None = None  # 发电机编号
    field_1: str | None = None  # 所属机组
    field_2: str | None = None  # 额定电压
    field_3: str | None = None  # 绝缘电阻
    field_4: str | None = None  # 轴承温度
    field_5: str | None = None  # 上次检测日
    field_6: str | None = None  # 检测结论
    field_7: str | None = None  # 发电机状态

class PitchEntry(BaseModel):
    """变桨系统明细结构。"""

    field_0: str | None = None  # 系统编号
    field_1: str | None = None  # 所属机组
    field_2: str | None = None  # 变桨方式
    field_3: str | None = None  # 桨距角范围
    field_4: str | None = None  # 蓄电池电压
    field_5: str | None = None  # 上次调试日
    field_6: str | None = None  # 调试人员
    field_7: str | None = None  # 变桨状态

class YawEntry(BaseModel):
    """偏航系统明细结构。"""

    field_0: str | None = None  # 系统编号
    field_1: str | None = None  # 所属机组
    field_2: str | None = None  # 偏航方式
    field_3: str | None = None  # 对风偏差
    field_4: str | None = None  # 偏航次数
    field_5: str | None = None  # 上次润滑日
    field_6: str | None = None  # 润滑油脂
    field_7: str | None = None  # 偏航状态

class MetmastEntry(BaseModel):
    """测风塔明细结构。"""

    field_0: str | None = None  # 塔架编号
    field_1: str | None = None  # 所在场站
    field_2: str | None = None  # 塔架高度
    field_3: str | None = None  # 测风层数
    field_4: str | None = None  # 风速仪型号
    field_5: str | None = None  # 上次校验日
    field_6: str | None = None  # 数据完整率
    field_7: str | None = None  # 测风状态

class CollectorEntry(BaseModel):
    """集电线路明细结构。"""

    field_0: str | None = None  # 线路编号
    field_1: str | None = None  # 电压等级
    field_2: str | None = None  # 起止杆塔
    field_3: str | None = None  # 线路长度
    field_4: str | None = None  # 所属场站
    field_5: str | None = None  # 上次巡视日
    field_6: str | None = None  # 缺陷数量
    field_7: str | None = None  # 线路状态

class SubstationEntry(BaseModel):
    """升压站明细结构。"""

    field_0: str | None = None  # 站区编号
    field_1: str | None = None  # 主变容量
    field_2: str | None = None  # 电压等级
    field_3: str | None = None  # 所属场站
    field_4: str | None = None  # 上次检修日
    field_5: str | None = None  # 值班班组
    field_6: str | None = None  # 负荷率
    field_7: str | None = None  # 升压站状态

class ForecastEntry(BaseModel):
    """功率预测单明细结构。"""

    field_0: str | None = None  # 预测单号
    field_1: str | None = None  # 所属场站
    field_2: str | None = None  # 预测日期
    field_3: str | None = None  # 预测出力
    field_4: str | None = None  # 实际出力
    field_5: str | None = None  # 预测偏差
    field_6: str | None = None  # 考核电量
    field_7: str | None = None  # 预测状态

class VibrationEntry(BaseModel):
    """振动监测记录明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 监测部位
    field_2: str | None = None  # 所属机组
    field_3: str | None = None  # 振动速度
    field_4: str | None = None  # 报警阈值
    field_5: str | None = None  # 采集时间
    field_6: str | None = None  # 频谱特征
    field_7: str | None = None  # 监测状态

class DefectEntry(BaseModel):
    """机组缺陷明细结构。"""

    field_0: str | None = None  # 缺陷编号
    field_1: str | None = None  # 缺陷部位
    field_2: str | None = None  # 缺陷等级
    field_3: str | None = None  # 发现方式
    field_4: str | None = None  # 发现时间
    field_5: str | None = None  # 报告人
    field_6: str | None = None  # 计划消除日
    field_7: str | None = None  # 缺陷状态

class MaintjobEntry(BaseModel):
    """检修任务单明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 关联机组
    field_2: str | None = None  # 检修类型
    field_3: str | None = None  # 计划开始日
    field_4: str | None = None  # 计划工时
    field_5: str | None = None  # 作业班组
    field_6: str | None = None  # 负责人
    field_7: str | None = None  # 任务状态

class SpareEntry(BaseModel):
    """备件领用单明细结构。"""

    field_0: str | None = None  # 领用单号
    field_1: str | None = None  # 备件名称
    field_2: str | None = None  # 备件规格
    field_3: str | None = None  # 领用数量
    field_4: str | None = None  # 领用班组
    field_5: str | None = None  # 领用日期
    field_6: str | None = None  # 所属场站
    field_7: str | None = None  # 领用状态

class PatrolEntry(BaseModel):
    """巡视单明细结构。"""

    field_0: str | None = None  # 巡视单号
    field_1: str | None = None  # 巡视路线
    field_2: str | None = None  # 巡视人员
    field_3: str | None = None  # 巡视日期
    field_4: str | None = None  # 发现问题数
    field_5: str | None = None  # 整改项数
    field_6: str | None = None  # 巡视时长
    field_7: str | None = None  # 巡视状态

class AcceptEntry(BaseModel):
    """验收单明细结构。"""

    field_0: str | None = None  # 验收单号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 验收项目
    field_3: str | None = None  # 验收标准
    field_4: str | None = None  # 验收结论
    field_5: str | None = None  # 验收人员
    field_6: str | None = None  # 验收日期
    field_7: str | None = None  # 验收状态

class SettleEntry(BaseModel):
    """电量结算单明细结构。"""

    field_0: str | None = None  # 结算单号
    field_1: str | None = None  # 结算周期
    field_2: str | None = None  # 所属场站
    field_3: str | None = None  # 上网电量
    field_4: str | None = None  # 结算电价
    field_5: str | None = None  # 补贴金额
    field_6: str | None = None  # 结算金额
    field_7: str | None = None  # 结算状态
