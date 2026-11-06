// 与 core/mcp/language_learning/services/subject_cards.py 的 fit_subject_into_frame 使用同一规则。
const SUBJECT_FRAME = { width: 410, height: 268 };

function fitSubjectIntoFrame(subjectWidth, subjectHeight, frame = SUBJECT_FRAME) {
  if (subjectWidth < 1 || subjectHeight < 1 || frame.width < 1 || frame.height < 1) {
    throw new Error("主体图或卡片主体区尺寸无效");
  }
  const scale = Math.min(frame.width / subjectWidth, frame.height / subjectHeight);
  const width = Math.max(1, Math.round(subjectWidth * scale));
  const height = Math.max(1, Math.round(subjectHeight * scale));
  return {
    width,
    height,
    left: Math.floor((frame.width - width) / 2),
    top: Math.floor((frame.height - height) / 2),
  };
}

function fitSubjectIntoFrameRatio(subjectWidth, subjectHeight, frame = SUBJECT_FRAME) {
  const fitted = fitSubjectIntoFrame(subjectWidth, subjectHeight, frame);
  return {
    width: `${fitted.width / frame.width * 100}%`,
    height: `${fitted.height / frame.height * 100}%`,
    left: `${fitted.left / frame.width * 100}%`,
    top: `${fitted.top / frame.height * 100}%`,
  };
}
